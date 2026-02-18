"""
Celery background tasks for async processing
"""

from celery import shared_task
from django.utils import timezone
from .models import Repository, User, PullRequest, Issue, Commit, Contributor
from .github_api import GitHubAPIClient
import logging

logger = logging.getLogger(__name__)


@shared_task
def sync_repository_data(repository_id):
    """
    Sync all data for a single repository
    """
    try:
        repository = Repository.objects.get(id=repository_id)
        user = repository.user
        
        if not user.github_access_token:
            logger.error(f"No access token for user {user.github_login}")
            return False
        
        client = GitHubAPIClient(user.github_access_token)
        
        # Sync repository details
        repo_data = client.get_repository_details(repository.full_name)
        if repo_data:
            repository.stars_count = repo_data['stargazers_count']
            repository.forks_count = repo_data['forks_count']
            repository.open_issues_count = repo_data['open_issues_count']
            repository.watchers_count = repo_data['watchers_count']
            repository.size = repo_data['size']
            repository.github_updated_at = repo_data['updated_at']
            repository.github_pushed_at = repo_data['pushed_at']
            repository.last_synced_at = timezone.now()
            repository.save()
        
        # Sync pull requests
        sync_pull_requests(repository_id)
        
        # Sync issues
        sync_issues(repository_id)
        
        # Sync commits
        sync_commits(repository_id)
        
        # Sync contributors
        sync_contributors(repository_id)
        
        logger.info(f"Successfully synced repository: {repository.full_name}")
        return True
        
    except Repository.DoesNotExist:
        logger.error(f"Repository {repository_id} not found")
        return False
    except Exception as e:
        logger.error(f"Error syncing repository {repository_id}: {e}")
        return False


@shared_task
def sync_pull_requests(repository_id):
    """
    Sync pull requests for repository
    """
    try:
        repository = Repository.objects.get(id=repository_id)
        user = repository.user
        
        client = GitHubAPIClient(user.github_access_token)
        pr_data = client.get_pull_requests(repository.full_name)
        
        for pr in pr_data:
            PullRequest.objects.update_or_create(
                repository=repository,
                number=pr['number'],
                defaults={
                    'github_id': str(pr['id']),
                    'title': pr['title'],
                    'body': pr['body'] or '',
                    'state': pr['state'],
                    'html_url': pr['html_url'],
                    'author_login': pr['author_login'],
                    'author_avatar_url': pr['author_avatar_url'],
                    'head_branch': pr['head_branch'],
                    'base_branch': pr['base_branch'],
                    'additions': pr['additions'],
                    'deletions': pr['deletions'],
                    'changed_files': pr['changed_files'],
                    'comments_count': pr['comments_count'],
                    'review_comments_count': pr['review_comments_count'],
                    'commits_count': pr['commits_count'],
                    'mergeable': pr['mergeable'],
                    'merged': pr['merged'],
                    'merged_at': pr['merged_at'],
                    'closed_at': pr['closed_at'],
                    'created_at': pr['created_at'],
                    'updated_at': pr['updated_at'],
                }
            )
        
        logger.info(f"Synced {len(pr_data)} pull requests for {repository.full_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error syncing pull requests: {e}")
        return False


@shared_task
def sync_issues(repository_id):
    """
    Sync issues for repository
    """
    try:
        repository = Repository.objects.get(id=repository_id)
        user = repository.user
        
        client = GitHubAPIClient(user.github_access_token)
        issue_data = client.get_issues(repository.full_name)
        
        for issue in issue_data:
            Issue.objects.update_or_create(
                repository=repository,
                number=issue['number'],
                defaults={
                    'github_id': str(issue['id']),
                    'title': issue['title'],
                    'body': issue['body'] or '',
                    'state': issue['state'],
                    'html_url': issue['html_url'],
                    'author_login': issue['author_login'],
                    'author_avatar_url': issue['author_avatar_url'],
                    'labels': issue['labels'],
                    'assignees': issue['assignees'],
                    'comments_count': issue['comments_count'],
                    'closed_at': issue['closed_at'],
                    'created_at': issue['created_at'],
                    'updated_at': issue['updated_at'],
                }
            )
        
        logger.info(f"Synced {len(issue_data)} issues for {repository.full_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error syncing issues: {e}")
        return False


@shared_task
def sync_commits(repository_id):
    """
    Sync commits for repository
    """
    try:
        repository = Repository.objects.get(id=repository_id)
        user = repository.user
        
        client = GitHubAPIClient(user.github_access_token)
        commit_data = client.get_commits(repository.full_name)
        
        for commit in commit_data:
            Commit.objects.update_or_create(
                sha=commit['sha'],
                defaults={
                    'repository': repository,
                    'message': commit['message'],
                    'html_url': commit['html_url'],
                    'author_name': commit['author_name'],
                    'author_email': commit['author_email'],
                    'author_login': commit['author_login'],
                    'author_avatar_url': commit['author_avatar_url'],
                    'additions': commit['additions'],
                    'deletions': commit['deletions'],
                    'total_changes': commit['total_changes'],
                    'committed_at': commit['committed_at'],
                }
            )
        
        logger.info(f"Synced {len(commit_data)} commits for {repository.full_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error syncing commits: {e}")
        return False


@shared_task
def sync_contributors(repository_id):
    """
    Sync contributors for repository
    """
    try:
        repository = Repository.objects.get(id=repository_id)
        user = repository.user
        
        client = GitHubAPIClient(user.github_access_token)
        contributor_data = client.get_contributors(repository.full_name)
        
        # Clear existing contributors
        repository.contributors.all().delete()
        
        for contributor in contributor_data:
            Contributor.objects.create(
                repository=repository,
                github_login=contributor['login'],
                avatar_url=contributor['avatar_url'],
                html_url=contributor['html_url'],
                contributions=contributor['contributions'],
            )
        
        logger.info(f"Synced {len(contributor_data)} contributors for {repository.full_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error syncing contributors: {e}")
        return False


@shared_task
def sync_all_repositories():
    """
    Periodic task to sync all active repositories
    """
    try:
        active_repos = Repository.objects.filter(is_active=True)
        
        for repo in active_repos:
            sync_repository_data.delay(repo.id)
        
        logger.info(f"Queued sync for {active_repos.count()} repositories")
        return True
        
    except Exception as e:
        logger.error(f"Error queuing repository syncs: {e}")
        return False
