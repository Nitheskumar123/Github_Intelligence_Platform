"""
GitHub API wrapper functions
Provides clean interface to interact with GitHub API
"""

from github import Github, GithubException
from django.conf import settings
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class GitHubAPIClient:
    """
    Wrapper for PyGithub to interact with GitHub API
    """
    
    def __init__(self, access_token):
        """
        Initialize GitHub client with access token
        """
        self.client = Github(access_token)
        self.access_token = access_token
    
    def get_user_info(self):
        """
        Get authenticated user information
        """
        try:
            user = self.client.get_user()
            return {
                'login': user.login,
                'id': user.id,
                'avatar_url': user.avatar_url,
                'html_url': user.html_url,
                'name': user.name,
                'email': user.email,
                'bio': user.bio,
                'company': user.company,
                'location': user.location,
            }
        except GithubException as e:
            logger.error(f"Error fetching user info: {e}")
            return None
    
    def get_repositories(self, affiliation='owner,collaborator,organization_member'):
        """
        Get user's repositories
        """
        try:
            user = self.client.get_user()
            repos = user.get_repos(affiliation=affiliation)
            
            repo_list = []
            for repo in repos:
                repo_list.append({
                    'id': repo.id,
                    'name': repo.name,
                    'full_name': repo.full_name,
                    'description': repo.description,
                    'html_url': repo.html_url,
                    'private': repo.private,
                    'fork': repo.fork,
                    'language': repo.language,
                    'stargazers_count': repo.stargazers_count,
                    'forks_count': repo.forks_count,
                    'open_issues_count': repo.open_issues_count,
                    'watchers_count': repo.watchers_count,
                    'default_branch': repo.default_branch,
                    'size': repo.size,
                    'has_issues': repo.has_issues,
                    'has_projects': repo.has_projects,
                    'has_wiki': repo.has_wiki,
                    'created_at': repo.created_at,
                    'updated_at': repo.updated_at,
                    'pushed_at': repo.pushed_at,
                })
            
            return repo_list
        except GithubException as e:
            logger.error(f"Error fetching repositories: {e}")
            return []
    
    def get_repository_details(self, full_name):
        """
        Get detailed repository information
        """
        try:
            repo = self.client.get_repo(full_name)
            return {
                'id': repo.id,
                'name': repo.name,
                'full_name': repo.full_name,
                'description': repo.description,
                'html_url': repo.html_url,
                'private': repo.private,
                'fork': repo.fork,
                'language': repo.language,
                'stargazers_count': repo.stargazers_count,
                'forks_count': repo.forks_count,
                'open_issues_count': repo.open_issues_count,
                'watchers_count': repo.watchers_count,
                'default_branch': repo.default_branch,
                'size': repo.size,
                'has_issues': repo.has_issues,
                'has_projects': repo.has_projects,
                'has_wiki': repo.has_wiki,
                'created_at': repo.created_at,
                'updated_at': repo.updated_at,
                'pushed_at': repo.pushed_at,
            }
        except GithubException as e:
            logger.error(f"Error fetching repository details: {e}")
            return None
    
    def get_pull_requests(self, full_name, state='all', limit=30):
        """
        Get pull requests for repository
        """
        try:
            repo = self.client.get_repo(full_name)
            pulls = repo.get_pulls(state=state, sort='updated', direction='desc')
            
            pr_list = []
            count = 0
            for pr in pulls:
                if count >= limit:
                    break
                count += 1
                try:
                    pr_list.append({
                        'id': pr.id,
                        'number': pr.number,
                        'title': pr.title,
                        'body': pr.body,
                        'state': pr.state,
                        'html_url': pr.html_url,
                        'author_login': pr.user.login if pr.user else 'unknown',
                        'author_avatar_url': pr.user.avatar_url if pr.user else None,
                        'head_branch': pr.head.ref if pr.head else 'deleted',
                        'base_branch': pr.base.ref if pr.base else 'deleted',
                        'additions': pr.additions or 0,
                        'deletions': pr.deletions or 0,
                        'changed_files': pr.changed_files or 0,
                        'comments_count': pr.comments or 0,
                        'review_comments_count': pr.review_comments or 0,
                        'commits_count': pr.commits or 0,
                        'mergeable': pr.mergeable,
                        'merged': pr.merged,
                        'merged_at': pr.merged_at,
                        'closed_at': pr.closed_at,
                        'created_at': pr.created_at,
                        'updated_at': pr.updated_at,
                    })
                except Exception as e:
                    logger.warning(f"Skipping PR #{pr.number} due to: {e}")
                    continue
            
            return pr_list
        except GithubException as e:
            logger.error(f"Error fetching pull requests: {e}")
            return []
    
    def get_issues(self, full_name, state='all', limit=30):
        """
        Get issues for repository (excluding pull requests)
        """
        try:
            repo = self.client.get_repo(full_name)
            issues = repo.get_issues(state=state, sort='updated', direction='desc')
            
            issue_list = []
            count = 0
            for issue in issues:
                # Skip pull requests (they show up in issues API)
                if issue.pull_request:
                    continue
                
                if count >= limit:
                    break
                count += 1
                
                try:
                    issue_list.append({
                        'id': issue.id,
                        'number': issue.number,
                        'title': issue.title,
                        'body': issue.body or '',
                        'state': issue.state,
                        'html_url': issue.html_url,
                        'author_login': issue.user.login if issue.user else 'unknown',
                        'author_avatar_url': issue.user.avatar_url if issue.user else None,
                        'labels': [{'name': label.name, 'color': label.color} for label in issue.labels],
                        'assignees': [assignee.login for assignee in issue.assignees],
                        'comments_count': issue.comments or 0,
                        'closed_at': issue.closed_at,
                        'created_at': issue.created_at,
                        'updated_at': issue.updated_at,
                    })
                except Exception as e:
                    logger.warning(f"Skipping issue #{issue.number} due to: {e}")
                    continue
            
            return issue_list
        except GithubException as e:
            logger.error(f"Error fetching issues: {e}")
            return []
    
    def get_commits(self, full_name, limit=30):
        """
        Get recent commits for repository
        """
        try:
            repo = self.client.get_repo(full_name)
            commits = repo.get_commits()
            
            commit_list = []
            count = 0
            for commit in commits:
                if count >= limit:
                    break
                count += 1
                try:
                    commit_list.append({
                    'sha': commit.sha,
                    'message': commit.commit.message,
                    'html_url': commit.html_url,
                    'author_name': commit.commit.author.name,
                    'author_email': commit.commit.author.email,
                    'author_login': commit.author.login if commit.author else None,
                    'author_avatar_url': commit.author.avatar_url if commit.author else None,
                    'additions': commit.stats.additions if commit.stats else 0,
                    'deletions': commit.stats.deletions if commit.stats else 0,
                    'total_changes': commit.stats.total if commit.stats else 0,
                    'committed_at': commit.commit.author.date,
                    })
                except Exception as e:
                    logger.warning(f"Skipping commit {commit.sha[:7]} due to: {e}")
                    continue
            
            return commit_list
        except GithubException as e:
            logger.error(f"Error fetching commits: {e}")
            return []
    
    def get_contributors(self, full_name):
        """
        Get repository contributors
        """
        try:
            repo = self.client.get_repo(full_name)
            contributors = repo.get_contributors()
            
            contributor_list = []
            for contributor in contributors:
                contributor_list.append({
                    'login': contributor.login,
                    'avatar_url': contributor.avatar_url,
                    'html_url': contributor.html_url,
                    'contributions': contributor.contributions,
                })
            
            return contributor_list
        except GithubException as e:
            logger.error(f"Error fetching contributors: {e}")
            return []
    
    def get_languages(self, full_name):
        """
        Get programming languages used in repository
        """
        try:
            repo = self.client.get_repo(full_name)
            languages = repo.get_languages()
            return languages
        except GithubException as e:
            logger.error(f"Error fetching languages: {e}")
            return {}
    
    def create_webhook(self, full_name, webhook_url, secret, events=None):
        """
        Create webhook for repository
        """
        if events is None:
            events = ['push', 'pull_request', 'issues']
        
        try:
            repo = self.client.get_repo(full_name)
            config = {
                'url': webhook_url,
                'content_type': 'json',
                'secret': secret,
            }
            
            hook = repo.create_hook(
                name='web',
                config=config,
                events=events,
                active=True
            )
            
            return {
                'id': hook.id,
                'url': hook.url,
                'events': hook.events,
                'active': hook.active,
            }
        except GithubException as e:
            logger.error(f"Error creating webhook: {e}")
            return None
    
    def delete_webhook(self, full_name, hook_id):
        """
        Delete webhook from repository
        """
        try:
            repo = self.client.get_repo(full_name)
            hook = repo.get_hook(int(hook_id))
            hook.delete()
            return True
        except GithubException as e:
            logger.error(f"Error deleting webhook: {e}")
            return False
    
    def get_rate_limit(self):
        """
        Get current API rate limit status
        """
        try:
            rate_limit = self.client.get_rate_limit()
            return {
                'core': {
                    'limit': rate_limit.core.limit,
                    'remaining': rate_limit.core.remaining,
                    'reset': rate_limit.core.reset,
                },
                'search': {
                    'limit': rate_limit.search.limit,
                    'remaining': rate_limit.search.remaining,
                    'reset': rate_limit.search.reset,
                }
            }
        except GithubException as e:
            logger.error(f"Error fetching rate limit: {e}")
            return None
