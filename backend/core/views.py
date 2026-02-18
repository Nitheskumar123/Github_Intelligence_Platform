import requests
import secrets
import json
from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth import login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .models import (
    User, Repository, PullRequest, Issue, Commit, 
    Contributor, RepositoryWebhook, GitHubOAuthState
)
from .serializers import (
    UserSerializer, RepositorySerializer, PullRequestSerializer,
    IssueSerializer, CommitSerializer, ContributorSerializer,
    RepositoryWebhookSerializer
)
from .github_api import GitHubAPIClient
from .webhooks import verify_webhook_signature, process_webhook_event
from .tasks import sync_repository_data


# ============================================================================
# GITHUB OAUTH VIEWS
# ============================================================================

@require_http_methods(["GET"])
def github_login(request):
    """
    Initiate GitHub OAuth flow
    Redirects user to GitHub authorization page
    """
    state = secrets.token_urlsafe(32)
    GitHubOAuthState.objects.create(state=state)
    GitHubOAuthState.cleanup_old_states()
    
    github_auth_url = (
        f"https://github.com/login/oauth/authorize?"
        f"client_id={settings.GITHUB_CLIENT_ID}&"
        f"redirect_uri={settings.GITHUB_REDIRECT_URI}&"
        f"scope=repo,user,read:org&"
        f"state={state}"
    )
    
    return redirect(github_auth_url)


@require_http_methods(["GET"])
def github_callback(request):
    """
    GitHub OAuth callback handler
    """
    code = request.GET.get('code')
    state = request.GET.get('state')
    
    try:
        oauth_state = GitHubOAuthState.objects.get(state=state, is_used=False)
        oauth_state.is_used = True
        oauth_state.save()
    except GitHubOAuthState.DoesNotExist:
        return JsonResponse({'error': 'Invalid state parameter'}, status=400)
    
    if not code:
        return JsonResponse({'error': 'No authorization code provided'}, status=400)
    
    # Exchange code for access token
    token_url = 'https://github.com/login/oauth/access_token'
    token_data = {
        'client_id': settings.GITHUB_CLIENT_ID,
        'client_secret': settings.GITHUB_CLIENT_SECRET,
        'code': code,
        'redirect_uri': settings.GITHUB_REDIRECT_URI,
    }
    token_headers = {'Accept': 'application/json'}
    
    try:
        token_response = requests.post(token_url, data=token_data, headers=token_headers)
        token_response.raise_for_status()
        token_json = token_response.json()
        access_token = token_json.get('access_token')
        
        if not access_token:
            return JsonResponse({'error': 'Failed to obtain access token'}, status=400)
        
    except requests.RequestException as e:
        return JsonResponse({'error': f'GitHub API error: {str(e)}'}, status=500)
    
    # Fetch user information
    user_url = 'https://api.github.com/user'
    user_headers = {'Authorization': f'token {access_token}', 'Accept': 'application/json'}
    
    try:
        user_response = requests.get(user_url, headers=user_headers)
        user_response.raise_for_status()
        github_user = user_response.json()
    except requests.RequestException as e:
        return JsonResponse({'error': f'Failed to fetch user data: {str(e)}'}, status=500)
    
    # Create or update user
    github_id = str(github_user.get('id'))
    github_login = github_user.get('login')
    
    user, created = User.objects.update_or_create(
        github_id=github_id,
        defaults={
            'github_login': github_login,
            'username': github_login,
            'github_access_token': access_token,
            'github_avatar_url': github_user.get('avatar_url'),
            'github_profile_url': github_user.get('html_url'),
            'github_bio': github_user.get('bio'),
            'github_company': github_user.get('company'),
            'github_location': github_user.get('location'),
            'email': github_user.get('email') or f'{github_login}@github.user',
            'first_name': github_user.get('name', '').split()[0] if github_user.get('name') else '',
            'last_name': ' '.join(github_user.get('name', '').split()[1:]) if github_user.get('name') else '',
        }
    )
    
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('/dashboard/')


# ============================================================================
# USER API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """Get current authenticated user information"""
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_user(request):
    """Logout current user"""
    logout(request)
    return Response({'message': 'Successfully logged out'}, status=status.HTTP_200_OK)


# ============================================================================
# REPOSITORY API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_repositories(request):
    """List all repositories for current user"""
    repositories = Repository.objects.filter(user=request.user)
    serializer = RepositorySerializer(repositories, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def repository_detail(request, repo_id):
    """Get detailed repository information"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        serializer = RepositorySerializer(repository)
        return Response(serializer.data)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_repositories(request):
    """Fetch and sync user's GitHub repositories"""
    user = request.user
    access_token = user.github_access_token
    
    if not access_token:
        return Response({'error': 'No GitHub access token found'}, status=400)
    
    client = GitHubAPIClient(access_token)
    github_repos = client.get_repositories()
    
    synced_count = 0
    for repo_data in github_repos:
        repository, created = Repository.objects.update_or_create(
            github_id=str(repo_data['id']),
            defaults={
                'user': user,
                'name': repo_data['name'],
                'full_name': repo_data['full_name'],
                'description': repo_data.get('description', ''),
                'html_url': repo_data['html_url'],
                'is_private': repo_data['private'],
                'is_fork': repo_data['fork'],
                'language': repo_data.get('language'),
                'stars_count': repo_data.get('stargazers_count', 0),
                'forks_count': repo_data.get('forks_count', 0),
                'open_issues_count': repo_data.get('open_issues_count', 0),
                'watchers_count': repo_data.get('watchers_count', 0),
                'default_branch': repo_data.get('default_branch', 'main'),
                'size': repo_data.get('size', 0),
                'has_issues': repo_data.get('has_issues', True),
                'has_projects': repo_data.get('has_projects', True),
                'has_wiki': repo_data.get('has_wiki', True),
                'github_created_at': repo_data.get('created_at'),
                'github_updated_at': repo_data.get('updated_at'),
                'github_pushed_at': repo_data.get('pushed_at'),
            }
        )
        synced_count += 1
    
    return Response({
        'message': f'Successfully synced {synced_count} repositories',
        'count': synced_count
    }, status=200)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_single_repository(request, repo_id):
    """Sync single repository data (PRs, issues, commits, etc.)"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        
        # Queue background task
        sync_repository_data.delay(repository.id)
        
        return Response({
            'message': f'Sync started for {repository.full_name}',
            'repository_id': repository.id
        }, status=202)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# PULL REQUEST API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_pull_requests(request, repo_id):
    """List pull requests for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        state = request.query_params.get('state', 'all')  # all, open, closed
        
        pull_requests = repository.pull_requests.all()
        if state != 'all':
            pull_requests = pull_requests.filter(state=state)
        
        serializer = PullRequestSerializer(pull_requests, many=True)
        return Response(serializer.data)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pull_request_detail(request, repo_id, pr_number):
    """Get pull request details"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        pull_request = repository.pull_requests.get(number=pr_number)
        serializer = PullRequestSerializer(pull_request)
        return Response(serializer.data)
    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'Pull request not found'}, status=404)


# ============================================================================
# ISSUE API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_issues(request, repo_id):
    """List issues for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        state = request.query_params.get('state', 'all')  # all, open, closed
        
        issues = repository.issues.all()
        if state != 'all':
            issues = issues.filter(state=state)
        
        serializer = IssueSerializer(issues, many=True)
        return Response(serializer.data)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def issue_detail(request, repo_id, issue_number):
    """Get issue details"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        issue = repository.issues.get(number=issue_number)
        serializer = IssueSerializer(issue)
        return Response(serializer.data)
    except (Repository.DoesNotExist, Issue.DoesNotExist):
        return Response({'error': 'Issue not found'}, status=404)


# ============================================================================
# COMMIT API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_commits(request, repo_id):
    """List recent commits for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        limit = int(request.query_params.get('limit', 30))
        
        commits = repository.commits.all()[:limit]
        serializer = CommitSerializer(commits, many=True)
        return Response(serializer.data)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# CONTRIBUTOR API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_contributors(request, repo_id):
    """List contributors for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        contributors = repository.contributors.all()
        serializer = ContributorSerializer(contributors, many=True)
        return Response(serializer.data)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# LANGUAGE STATS API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def repository_languages(request, repo_id):
    """Get language statistics for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        user = request.user
        
        client = GitHubAPIClient(user.github_access_token)
        languages = client.get_languages(repository.full_name)
        
        return Response(languages)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# ACTIVITY FEED API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def repository_activity(request, repo_id):
    """Get combined activity feed for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        
        # Get recent webhook events
        webhook_events = repository.webhook_events.all()[:20]
        
        activity_feed = []
        for event in webhook_events:
            activity_feed.append({
                'type': event.event_type,
                'timestamp': event.created_at,
                'processed': event.processed,
                'data': event.payload
            })
        
        return Response(activity_feed)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# WEBHOOK API VIEWS
# ============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def setup_webhook(request, repo_id):
    """Setup webhook for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        user = request.user
        
        # Generate webhook secret
        webhook_secret = secrets.token_urlsafe(32)
        
        # Webhook URL (you'll need to replace with your actual domain in production)
        webhook_url = f"{settings.FRONTEND_URL}/api/webhooks/github/"
        
        # Create webhook on GitHub
        client = GitHubAPIClient(user.github_access_token)
        webhook_data = client.create_webhook(
            repository.full_name,
            webhook_url,
            webhook_secret,
            events=['push', 'pull_request', 'issues']
        )
        
        if not webhook_data:
            return Response({'error': 'Failed to create webhook'}, status=500)
        
        # Store webhook info in database
        webhook, created = RepositoryWebhook.objects.update_or_create(
            repository=repository,
            defaults={
                'github_webhook_id': str(webhook_data['id']),
                'webhook_url': webhook_url,
                'secret': webhook_secret,
                'events': webhook_data['events'],
                'is_active': webhook_data['active'],
            }
        )
        
        serializer = RepositoryWebhookSerializer(webhook)
        return Response(serializer.data, status=201)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def webhook_status(request, repo_id):
    """Get webhook status for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        
        if not hasattr(repository, 'webhook'):
            return Response({'has_webhook': False})
        
        webhook = repository.webhook
        serializer = RepositoryWebhookSerializer(webhook)
        return Response({
            'has_webhook': True,
            'webhook': serializer.data
        })
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
def github_webhook_receiver(request):
    """
    Receive and process GitHub webhook events
    """
    # Get headers
    event_type = request.headers.get('X-GitHub-Event')
    delivery_id = request.headers.get('X-GitHub-Delivery')
    signature = request.headers.get('X-Hub-Signature-256')
    
    if not all([event_type, delivery_id, signature]):
        return JsonResponse({'error': 'Missing required headers'}, status=400)
    
    # Get payload
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
    
    # Get repository info
    repository_data = payload.get('repository', {})
    repository_full_name = repository_data.get('full_name')
    
    if not repository_full_name:
        return JsonResponse({'error': 'Repository not found in payload'}, status=400)
    
    # Find repository in database
    try:
        repository = Repository.objects.get(full_name=repository_full_name)
        
        if not hasattr(repository, 'webhook'):
            return JsonResponse({'error': 'Webhook not configured'}, status=400)
        
        webhook_secret = repository.webhook.secret
        
    except Repository.DoesNotExist:
        return JsonResponse({'error': 'Repository not found'}, status=404)
    
    # Verify signature
    if not verify_webhook_signature(request.body, signature, webhook_secret):
        return JsonResponse({'error': 'Invalid signature'}, status=401)
    
    # Process webhook event
    process_webhook_event(event_type, delivery_id, payload, repository_full_name)
    
    return JsonResponse({'status': 'success'}, status=200)


# ============================================================================
# HEALTH CHECK
# ============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint"""
    return Response({
        'status': 'healthy',
        'message': 'GitHub Intelligence Platform API is running'
    }, status=200)
