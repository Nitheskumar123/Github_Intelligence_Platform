import requests
import secrets
from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth import login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .models import User, Repository, GitHubOAuthState
from .serializers import UserSerializer, RepositorySerializer


# ============================================================================
# GITHUB OAUTH VIEWS
# ============================================================================

@require_http_methods(["GET"])
def github_login(request):
    """
    Initiate GitHub OAuth flow
    Redirects user to GitHub authorization page
    """
    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store state in database
    GitHubOAuthState.objects.create(state=state)
    
    # Clean up old states
    GitHubOAuthState.cleanup_old_states()
    
    # Build GitHub authorization URL
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
    Exchanges authorization code for access token
    Creates or updates user account
    """
    code = request.GET.get('code')
    state = request.GET.get('state')
    
    # Validate state parameter
    try:
        oauth_state = GitHubOAuthState.objects.get(state=state, is_used=False)
        oauth_state.is_used = True
        oauth_state.save()
    except GitHubOAuthState.DoesNotExist:
        return JsonResponse({
            'error': 'Invalid state parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not code:
        return JsonResponse({
            'error': 'No authorization code provided'
        }, status=status.HTTP_400_BAD_REQUEST)
    
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
            return JsonResponse({
                'error': 'Failed to obtain access token'
            }, status=status.HTTP_400_BAD_REQUEST)
        
    except requests.RequestException as e:
        return JsonResponse({
            'error': f'GitHub API error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Fetch user information from GitHub
    user_url = 'https://api.github.com/user'
    user_headers = {
        'Authorization': f'token {access_token}',
        'Accept': 'application/json'
    }
    
    try:
        user_response = requests.get(user_url, headers=user_headers)
        user_response.raise_for_status()
        github_user = user_response.json()
        
    except requests.RequestException as e:
        return JsonResponse({
            'error': f'Failed to fetch user data: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
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
    
    # Log the user in
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    
    # Redirect to dashboard
    return redirect('/dashboard/')


# ============================================================================
# API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def current_user(request):
    """
    Get current authenticated user information
    Returns user data if authenticated, or null if not
    """
    if request.user.is_authenticated:
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    else:
        # Return null/empty response with 200 status for unauthenticated users
        # This prevents 403 errors on initial page load
        return Response({'id': None}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_user(request):
    """
    Logout current user
    """
    logout(request)
    return Response({
        'message': 'Successfully logged out'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_repositories(request):
    """
    Fetch and sync user's GitHub repositories
    """
    user = request.user
    access_token = user.github_access_token
    
    if not access_token:
        return Response({
            'error': 'No GitHub access token found'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Fetch repositories from GitHub
    repos_url = 'https://api.github.com/user/repos'
    headers = {
        'Authorization': f'token {access_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    params = {
        'per_page': 100,
        'sort': 'updated',
        'affiliation': 'owner,collaborator,organization_member'
    }
    
    try:
        response = requests.get(repos_url, headers=headers, params=params)
        response.raise_for_status()
        github_repos = response.json()
        
    except requests.RequestException as e:
        return Response({
            'error': f'Failed to fetch repositories: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Sync repositories to database
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
                'github_created_at': repo_data.get('created_at'),
                'github_updated_at': repo_data.get('updated_at'),
            }
        )
        synced_count += 1
    
    return Response({
        'message': f'Successfully synced {synced_count} repositories',
        'count': synced_count
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_repositories(request):
    """
    List all repositories for current user
    """
    repositories = Repository.objects.filter(user=request.user)
    serializer = RepositorySerializer(repositories, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint
    """
    return Response({
        'status': 'healthy',
        'message': 'GitHub Intelligence Platform API is running'
    }, status=status.HTTP_200_OK)
