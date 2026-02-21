"""
Celery Background Tasks
Handles asynchronous processing for GitHub syncing, Groq AI analysis, and insight generation.
"""

import logging
import asyncio
import base64
import requests
from typing import List, Dict, Any, Optional

from celery import shared_task
from django.utils import timezone
from django.db import transaction
from requests.exceptions import RequestException

from .models import (
    Repository, User, PullRequest, Issue, 
    Commit, Contributor, DocumentationGeneration
)
from .github_api import GitHubAPIClient

logger = logging.getLogger(__name__)

# ============================================================================
# REPOSITORY SYNCING TASKS
# ============================================================================

@shared_task(bind=True, autoretry_for=(RequestException,), retry_backoff=True, max_retries=3)
def sync_repository_data(self, repository_id: int) -> bool:
    """
    Master task to sync all data for a single repository.
    Triggers sub-tasks for PRs, issues, commits, and contributors.
    """
    try:
        repository = Repository.objects.select_related('user').get(id=repository_id)
        user = repository.user
        
        if not user.github_access_token:
            logger.error(f"Sync aborted: No GitHub access token for user {user.github_login}")
            return False
            
        logger.info(f"Starting full sync for repository: {repository.full_name}")
        client = GitHubAPIClient(user.github_access_token)
        
        # 1. Sync core repository metadata
        repo_data = client.get_repository_details(repository.full_name)
        if repo_data:
            repository.stars_count = repo_data.get('stargazers_count', 0)
            repository.forks_count = repo_data.get('forks_count', 0)
            repository.open_issues_count = repo_data.get('open_issues_count', 0)
            repository.watchers_count = repo_data.get('watchers_count', 0)
            repository.size = repo_data.get('size', 0)
            repository.default_branch = repo_data.get('default_branch', 'main')
            repository.github_updated_at = repo_data.get('updated_at')
            repository.github_pushed_at = repo_data.get('pushed_at')
            repository.last_synced_at = timezone.now()
            repository.save()
        
        # 2. Trigger specialized syncs synchronously to ensure data integrity
        sync_pull_requests(repository_id)
        sync_issues(repository_id)
        sync_commits(repository_id)
        sync_contributors(repository_id)
        
        logger.info(f"Successfully completed full sync for repository: {repository.full_name}")
        return True
        
    except Repository.DoesNotExist:
        logger.error(f"Sync failed: Repository {repository_id} not found in database.")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during repository {repository_id} sync: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(bind=True, autoretry_for=(RequestException,), retry_backoff=True)
def sync_pull_requests(self, repository_id: int) -> bool:
    """Sync all pull requests for a given repository."""
    try:
        repository = Repository.objects.get(id=repository_id)
        client = GitHubAPIClient(repository.user.github_access_token)
        pr_data = client.get_pull_requests(repository.full_name)
        
        if not pr_data:
            return True
            
        with transaction.atomic():
            for pr in pr_data:
                PullRequest.objects.update_or_create(
                    repository=repository,
                    number=pr.get('number'),
                    defaults={
                        'github_id': str(pr.get('id')),
                        'title': pr.get('title', '')[:500],
                        'body': pr.get('body') or '',
                        'state': pr.get('state', 'unknown'),
                        'html_url': pr.get('html_url', ''),
                        'author_login': pr.get('author_login', ''),
                        'author_avatar_url': pr.get('author_avatar_url'),
                        'head_branch': pr.get('head_branch', '')[:255],
                        'base_branch': pr.get('base_branch', '')[:255],
                        'additions': pr.get('additions', 0),
                        'deletions': pr.get('deletions', 0),
                        'changed_files': pr.get('changed_files', 0),
                        'comments_count': pr.get('comments_count', 0),
                        'review_comments_count': pr.get('review_comments_count', 0),
                        'commits_count': pr.get('commits_count', 0),
                        'mergeable': pr.get('mergeable'),
                        'merged': pr.get('merged', False),
                        'merged_at': pr.get('merged_at'),
                        'closed_at': pr.get('closed_at'),
                        'created_at': pr.get('created_at'),
                        'updated_at': pr.get('updated_at'),
                        'synced_at': timezone.now()
                    }
                )
        
        logger.info(f"Successfully synced {len(pr_data)} pull requests for {repository.full_name}")
        return True
    except Exception as e:
        logger.error(f"Error syncing pull requests for repo {repository_id}: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, autoretry_for=(RequestException,), retry_backoff=True)
def sync_issues(self, repository_id: int) -> bool:
    """Sync all issues (excluding PRs) for a given repository."""
    try:
        repository = Repository.objects.get(id=repository_id)
        client = GitHubAPIClient(repository.user.github_access_token)
        issue_data = client.get_issues(repository.full_name)
        
        with transaction.atomic():
            for issue in issue_data:
                # GitHub API returns PRs as issues too; skip them here as they are handled by sync_pull_requests
                if 'pull_request' in issue:
                    continue
                    
                Issue.objects.update_or_create(
                    repository=repository,
                    number=issue.get('number'),
                    defaults={
                        'github_id': str(issue.get('id')),
                        'title': issue.get('title', '')[:500],
                        'body': issue.get('body') or '',
                        'state': issue.get('state', 'unknown'),
                        'html_url': issue.get('html_url', ''),
                        'author_login': issue.get('author_login', ''),
                        'author_avatar_url': issue.get('author_avatar_url'),
                        'labels': issue.get('labels', []),
                        'assignees': issue.get('assignees', []),
                        'comments_count': issue.get('comments_count', 0),
                        'closed_at': issue.get('closed_at'),
                        'created_at': issue.get('created_at'),
                        'updated_at': issue.get('updated_at'),
                        'synced_at': timezone.now()
                    }
                )
        
        logger.info(f"Successfully synced {len(issue_data)} issues for {repository.full_name}")
        return True
    except Exception as e:
        logger.error(f"Error syncing issues for repo {repository_id}: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, autoretry_for=(RequestException,), retry_backoff=True)
def sync_commits(self, repository_id: int) -> bool:
    """Sync recent commits for a given repository."""
    try:
        repository = Repository.objects.get(id=repository_id)
        client = GitHubAPIClient(repository.user.github_access_token)
        commit_data = client.get_commits(repository.full_name)
        
        with transaction.atomic():
            for commit in commit_data:
                Commit.objects.update_or_create(
                    sha=commit.get('sha'),
                    defaults={
                        'repository': repository,
                        'message': commit.get('message', ''),
                        'html_url': commit.get('html_url', ''),
                        'author_name': commit.get('author_name', 'Unknown')[:255],
                        'author_email': commit.get('author_email', '')[:255],
                        'author_login': commit.get('author_login'),
                        'author_avatar_url': commit.get('author_avatar_url'),
                        'additions': commit.get('additions', 0),
                        'deletions': commit.get('deletions', 0),
                        'total_changes': commit.get('total_changes', 0),
                        'committed_at': commit.get('committed_at'),
                        'synced_at': timezone.now()
                    }
                )
        
        logger.info(f"Successfully synced {len(commit_data)} commits for {repository.full_name}")
        return True
    except Exception as e:
        logger.error(f"Error syncing commits for repo {repository_id}: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, autoretry_for=(RequestException,), retry_backoff=True)
def sync_contributors(self, repository_id: int) -> bool:
    """Sync contributors and their contribution counts."""
    try:
        repository = Repository.objects.get(id=repository_id)
        client = GitHubAPIClient(repository.user.github_access_token)
        contributor_data = client.get_contributors(repository.full_name)
        
        with transaction.atomic():
            # Clear existing to prevent stale contributor data
            repository.contributors.all().delete()
            
            bulk_contributors = []
            for contributor in contributor_data:
                bulk_contributors.append(Contributor(
                    repository=repository,
                    github_login=contributor.get('login', 'Unknown')[:100],
                    avatar_url=contributor.get('avatar_url'),
                    html_url=contributor.get('html_url', ''),
                    contributions=contributor.get('contributions', 0),
                ))
            
            Contributor.objects.bulk_create(bulk_contributors)
        
        logger.info(f"Successfully synced {len(contributor_data)} contributors for {repository.full_name}")
        return True
    except Exception as e:
        logger.error(f"Error syncing contributors for repo {repository_id}: {e}")
        raise self.retry(exc=e)


@shared_task
def sync_all_repositories() -> bool:
    """Periodic task to trigger syncs for all active repositories globally."""
    try:
        active_repos = Repository.objects.filter(is_active=True)
        count = 0
        
        for repo in active_repos:
            # Dispatch async celery task for each repo
            sync_repository_data.delay(repo.id)
            count += 1
            
        logger.info(f"Successfully queued background sync for {count} active repositories")
        return True
    except Exception as e:
        logger.error(f"Fatal error queuing global repository syncs: {e}")
        return False


# ============================================================================
# GROQ AI CODE ANALYSIS TASKS
# ============================================================================

@shared_task(bind=True)
def analyze_pull_request(self, pr_id: int) -> bool:
    """
    Analyze a pull request's git diff using Groq AI.
    Runs the AsyncGroqCodeAnalyzer inside a synchronous Celery task.
    """
    try:
        from .code_review import AsyncGroqCodeAnalyzer
        from .models import PullRequest, PRAnalysis
        
        pr = PullRequest.objects.select_related('repository__user').get(id=pr_id)
        repository = pr.repository
        user = repository.user
        
        logger.info(f"Starting Groq AI analysis for PR #{pr.number} in {repository.full_name}")
        
        # 1. Fetch the raw Git Diff from GitHub API
        headers = {
            'Authorization': f'token {user.github_access_token}',
            'Accept': 'application/vnd.github.v3.diff' # Request diff format
        }
        diff_url = f"https://api.github.com/repos/{repository.full_name}/pulls/{pr.number}"
        
        response = requests.get(diff_url, headers=headers, timeout=30)
        response.raise_for_status()
        diff_content = response.text
        
        if not diff_content:
            logger.warning(f"No diff content found for PR #{pr.number}. Skipping analysis.")
            return False

        # 2. Prepare Context for Groq
        pr_context = {
            'title': pr.title,
            'description': pr.body,
            'files_changed': pr.changed_files,
            'additions': pr.additions,
            'deletions': pr.deletions
        }

        # 3. Run the Async Groq Analyzer using asyncio
        analyzer = AsyncGroqCodeAnalyzer()
        
        # We must create an event loop to run the async function in a sync celery worker
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(analyzer.analyze_pr_diff(diff_content, pr_context))
        finally:
            loop.close()
            
        if not result.get('success'):
            logger.error(f"Groq Analysis failed for PR #{pr.number}: {result.get('error')}")
            return False
            
        analysis_data = result.get('analysis', {})
        
        # 4. Save Results to Database
        PRAnalysis.objects.update_or_create(
            pull_request=pr,
            defaults={
                'summary': analysis_data.get('summary', 'No summary provided.'),
                'issues_found': len(analysis_data.get('security_issues', [])) + len(analysis_data.get('performance_issues', [])),
                'complexity_score': analysis_data.get('complexity_score', 0),
                'security_issues': analysis_data.get('security_issues', []),
                'performance_issues': analysis_data.get('performance_issues', []),
                'code_smells': analysis_data.get('code_smells', []),
                'positive_points': analysis_data.get('positive_points', []),
                'analysis_time': result.get('analysis_time', 0.0),
                'tokens_used': result.get('tokens_used', 0)
            }
        )
        
        logger.info(f"Successfully completed Groq analysis for PR #{pr.number}")
        return True
        
    except PullRequest.DoesNotExist:
        logger.error(f"Pull request {pr_id} not found in database.")
        return False
    except RequestException as e:
        logger.error(f"Network error fetching diff for PR {pr_id}: {e}")
        raise self.retry(exc=e, countdown=60)
    except Exception as e:
        logger.error(f"Unexpected error analyzing PR {pr_id}: {e}", exc_info=True)
        return False


# ============================================================================
# GROQ AI DOCUMENTATION GENERATION TASKS
# ============================================================================

@shared_task(bind=True)
def generate_repository_documentation(self, repo_id: int, doc_type: str = 'readme') -> bool:
    """
    Generate rich documentation (README, API, Contributing, Changelog) using Groq AI.
    """
    try:
        from .documentation_gen import GroqDocumentationGenerator
        
        repo = Repository.objects.select_related('user').get(id=repo_id)
        user = repo.user
        
        logger.info(f"Initiating {doc_type.upper()} generation for {repo.full_name}")
        
        # 1. Initialize the Documentation record as processing
        doc_gen = DocumentationGeneration.objects.create(
            repository=repo,
            user=user,
            doc_type=doc_type,
            status='processing'
        )
        
        # 2. Fetch Code Context
        client = GitHubAPIClient(user.github_access_token)
        
        if doc_type == 'changelog':
            # Changelog only needs commit history, not files
            context_data = client.get_commits(repo.full_name)
        else:
            # Readme, API, and Contributing need file structures
            context_data = fetch_repository_files(client, repo, max_files=15)
            if not context_data:
                doc_gen.status = 'failed'
                doc_gen.error_message = "Could not fetch codebase files. Repository may be empty."
                doc_gen.save()
                return False

        # 3. Generate Documentation with Groq
        generator = GroqDocumentationGenerator()
        
        if doc_type == 'readme':
            result = generator.generate_readme(repo, context_data)
        elif doc_type == 'api':
            result = generator.generate_api_documentation(context_data)
        elif doc_type == 'contributing':
            result = generator.generate_contributing_guide(repo, context_data)
        elif doc_type == 'changelog':
            result = generator.generate_changelog(context_data, repo)
        else:
            raise ValueError(f"Unsupported documentation type requested: {doc_type}")
            
        # 4. Save Results
        if result.get('success'):
            doc_gen.status = 'completed'
            doc_gen.content = result.get('content')
            doc_gen.tokens_used = result.get('tokens_used', 0)
            doc_gen.generation_time = result.get('generation_time', 0.0)
            doc_gen.completed_at = timezone.now()
            doc_gen.save()
            logger.info(f"Successfully generated {doc_type} for {repo.full_name}")
            return True
        else:
            doc_gen.status = 'failed'
            doc_gen.error_message = result.get('error', 'Unknown generation error')
            doc_gen.save()
            logger.error(f"Documentation generation failed for {repo.full_name}: {doc_gen.error_message}")
            return False
            
    except Repository.DoesNotExist:
        logger.error(f"Repository {repo_id} not found.")
        return False
    except Exception as e:
        logger.error(f"Fatal error generating {doc_type} for repo {repo_id}: {e}", exc_info=True)
        return False


# ============================================================================
# GROQ AI INSIGHTS TASKS
# ============================================================================

@shared_task
def generate_insights_for_user(user_id: int) -> int:
    """Generate proactive insights for all repositories owned by a user."""
    try:
        from .insights_engine import GroqInsightsEngine
        
        user = User.objects.get(id=user_id)
        logger.info(f"Starting bulk insight generation for user: {user.github_login}")
        
        engine = GroqInsightsEngine()
        total_insights = engine.generate_all_insights(user)
        
        logger.info(f"Successfully generated {total_insights} insights across {user.github_login}'s repositories")
        return total_insights
        
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found.")
        return 0
    except Exception as e:
        logger.error(f"Error during bulk insight generation for user {user_id}: {e}", exc_info=True)
        return 0


@shared_task
def generate_insights_for_repository(repo_id: int) -> int:
    """Generate proactive insights for a single repository."""
    try:
        from .insights_engine import GroqInsightsEngine
        
        repo = Repository.objects.get(id=repo_id)
        logger.info(f"Starting insight generation for repository: {repo.full_name}")
        
        engine = GroqInsightsEngine()
        insights = engine.generate_repository_insights(repo)
        
        count = len(insights)
        logger.info(f"Generated {count} insights for {repo.full_name}")
        return count
        
    except Repository.DoesNotExist:
        logger.error(f"Repository {repo_id} not found.")
        return 0
    except Exception as e:
        logger.error(f"Error generating insights for repository {repo_id}: {e}", exc_info=True)
        return 0


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def fetch_repository_files(client: GitHubAPIClient, repository: Repository, max_files: int = 15) -> List[Dict[str, str]]:
    """
    Fetch source code files from the repository using the GitHub Git Tree API.
    This method recursively fetches files from subdirectories, unlike the basic contents API.
    
    Args:
        client (GitHubAPIClient): Configured GitHub API client.
        repository (Repository): The repository to fetch from.
        max_files (int): Maximum number of source code files to retrieve.
        
    Returns:
        List[Dict[str, str]]: List containing dicts with 'path' and 'content'.
    """
    try:
        # 1. Get the default branch (usually 'main' or 'master')
        branch = repository.default_branch or 'main'
        
        # 2. Fetch the recursive git tree
        tree_url = f"https://api.github.com/repos/{repository.full_name}/git/trees/{branch}?recursive=1"
        headers = {
            'Authorization': f'token {client.access_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        tree_response = requests.get(tree_url, headers=headers, timeout=20)
        tree_response.raise_for_status()
        tree_data = tree_response.json()
        
        if getattr(tree_data, 'truncated', False):
            logger.warning(f"Git tree for {repository.full_name} was truncated. Some files may be missing.")
            
        # 3. Filter for valuable source code files, ignore binaries and heavy assets
        valid_extensions = (
            '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rs', 
            '.rb', '.php', '.cpp', '.c', '.h', '.cs', '.swift', '.kt',
            '.yml', '.yaml', '.json', '.md', '.toml', 'Dockerfile'
        )
        
        ignored_dirs = ('node_modules/', 'venv/', 'env/', '.git/', 'build/', 'dist/', 'target/', 'out/')
        
        file_nodes = []
        for item in tree_data.get('tree', []):
            if item.get('type') == 'blob': # 'blob' means it's a file
                path = item.get('path', '')
                
                # Skip ignored directories
                if any(ignored in path for ignored in ignored_dirs):
                    continue
                    
                # Check for valid extensions or exact matches like Dockerfile
                if path.endswith(valid_extensions) or path.endswith('Makefile'):
                    file_nodes.append(item)

        # 4. Fetch the actual content for the filtered files (up to max_files limit)
        code_files = []
        for node in file_nodes[:max_files]:
            blob_url = node.get('url')
            if not blob_url:
                continue
                
            blob_response = requests.get(blob_url, headers=headers, timeout=10)
            if blob_response.status_code == 200:
                blob_data = blob_response.json()
                
                # GitHub returns blob content encoded in Base64
                if blob_data.get('encoding') == 'base64':
                    try:
                        raw_content = base64.b64decode(blob_data.get('content', '')).decode('utf-8')
                        code_files.append({
                            'path': node.get('path'),
                            'content': raw_content[:8000] # Cap individual file size to prevent memory bloat
                        })
                    except UnicodeDecodeError:
                        logger.warning(f"Skipped {node.get('path')} due to decoding error (likely a binary file).")
                        
        return code_files
        
    except RequestException as e:
        logger.error(f"Network error fetching tree for {repository.full_name}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in fetch_repository_files for {repository.full_name}: {e}", exc_info=True)
        return []