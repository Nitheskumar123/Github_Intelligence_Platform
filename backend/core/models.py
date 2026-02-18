from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser
    Stores GitHub OAuth information
    """
    github_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    github_login = models.CharField(max_length=100, unique=True, null=True, blank=True)
    github_access_token = models.CharField(max_length=255, null=True, blank=True)
    github_avatar_url = models.URLField(max_length=500, null=True, blank=True)
    github_profile_url = models.URLField(max_length=500, null=True, blank=True)
    github_bio = models.TextField(null=True, blank=True)
    github_company = models.CharField(max_length=200, null=True, blank=True)
    github_location = models.CharField(max_length=200, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return self.github_login or self.username


class Repository(models.Model):
    """
    GitHub Repository model
    Stores basic repository information
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='repositories')
    
    # GitHub repository data
    github_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    html_url = models.URLField(max_length=500)
    
    # Repository metadata
    is_private = models.BooleanField(default=False)
    is_fork = models.BooleanField(default=False)
    language = models.CharField(max_length=100, null=True, blank=True)
    stars_count = models.IntegerField(default=0)
    forks_count = models.IntegerField(default=0)
    open_issues_count = models.IntegerField(default=0)
    watchers_count = models.IntegerField(default=0)
    
    # Additional details (Phase 1)
    default_branch = models.CharField(max_length=100, default='main')
    size = models.IntegerField(default=0)  # in KB
    has_issues = models.BooleanField(default=True)
    has_projects = models.BooleanField(default=True)
    has_wiki = models.BooleanField(default=True)
    
    # Tracking
    is_active = models.BooleanField(default=True)
    webhook_id = models.CharField(max_length=100, null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    github_created_at = models.DateTimeField(null=True, blank=True)
    github_updated_at = models.DateTimeField(null=True, blank=True)
    github_pushed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'repositories'
        verbose_name = 'Repository'
        verbose_name_plural = 'Repositories'
        ordering = ['-github_updated_at']
    
    def __str__(self):
        return self.full_name


class PullRequest(models.Model):
    """
    GitHub Pull Request model
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='pull_requests')
    
    # PR data
    github_id = models.CharField(max_length=100)
    number = models.IntegerField()
    title = models.CharField(max_length=500)
    body = models.TextField(null=True, blank=True)
    state = models.CharField(max_length=20)  # open, closed, merged
    html_url = models.URLField(max_length=500)
    
    # Author info
    author_login = models.CharField(max_length=100)
    author_avatar_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Branches
    head_branch = models.CharField(max_length=255)
    base_branch = models.CharField(max_length=255)
    
    # Stats
    additions = models.IntegerField(default=0)
    deletions = models.IntegerField(default=0)
    changed_files = models.IntegerField(default=0)
    comments_count = models.IntegerField(default=0)
    review_comments_count = models.IntegerField(default=0)
    commits_count = models.IntegerField(default=0)
    
    # Status
    mergeable = models.BooleanField(null=True, blank=True)
    merged = models.BooleanField(default=False)
    merged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    synced_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'pull_requests'
        unique_together = ['repository', 'number']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"#{self.number}: {self.title}"


class Issue(models.Model):
    """
    GitHub Issue model
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='issues')
    
    # Issue data
    github_id = models.CharField(max_length=100)
    number = models.IntegerField()
    title = models.CharField(max_length=500)
    body = models.TextField(null=True, blank=True)
    state = models.CharField(max_length=20)  # open, closed
    html_url = models.URLField(max_length=500)
    
    # Author info
    author_login = models.CharField(max_length=100)
    author_avatar_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Metadata
    labels = models.JSONField(default=list, blank=True)
    assignees = models.JSONField(default=list, blank=True)
    comments_count = models.IntegerField(default=0)
    
    # Status
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    synced_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'issues'
        unique_together = ['repository', 'number']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"#{self.number}: {self.title}"


class Commit(models.Model):
    """
    GitHub Commit model
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='commits')
    
    # Commit data
    sha = models.CharField(max_length=40, unique=True)
    message = models.TextField()
    html_url = models.URLField(max_length=500)
    
    # Author info
    author_name = models.CharField(max_length=255)
    author_email = models.CharField(max_length=255)
    author_login = models.CharField(max_length=100, null=True, blank=True)
    author_avatar_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Stats
    additions = models.IntegerField(default=0)
    deletions = models.IntegerField(default=0)
    total_changes = models.IntegerField(default=0)
    
    # Timestamp
    committed_at = models.DateTimeField()
    synced_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'commits'
        ordering = ['-committed_at']
    
    def __str__(self):
        return f"{self.sha[:7]}: {self.message[:50]}"


class Contributor(models.Model):
    """
    Repository Contributor model
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='contributors')
    
    # Contributor data
    github_login = models.CharField(max_length=100)
    avatar_url = models.URLField(max_length=500, null=True, blank=True)
    html_url = models.URLField(max_length=500)
    
    # Stats
    contributions = models.IntegerField(default=0)
    
    # Timestamp
    synced_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'contributors'
        unique_together = ['repository', 'github_login']
        ordering = ['-contributions']
    
    def __str__(self):
        return f"{self.github_login} ({self.contributions} contributions)"


class RepositoryWebhook(models.Model):
    """
    GitHub Webhook configuration for repository
    """
    repository = models.OneToOneField(Repository, on_delete=models.CASCADE, related_name='webhook')
    
    # Webhook data
    github_webhook_id = models.CharField(max_length=100)
    webhook_url = models.URLField(max_length=500)
    secret = models.CharField(max_length=100)
    
    # Configuration
    events = models.JSONField(default=list)  # List of subscribed events
    is_active = models.BooleanField(default=True)
    
    # Stats
    last_delivery_at = models.DateTimeField(null=True, blank=True)
    total_deliveries = models.IntegerField(default=0)
    failed_deliveries = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'repository_webhooks'
    
    def __str__(self):
        return f"Webhook for {self.repository.full_name}"


class WebhookEvent(models.Model):
    """
    GitHub Webhook Event log
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='webhook_events')
    
    # Event data
    event_type = models.CharField(max_length=50)  # push, pull_request, issues, etc.
    delivery_id = models.CharField(max_length=100, unique=True)
    payload = models.JSONField()
    
    # Processing status
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'webhook_events'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.event_type} - {self.delivery_id}"


class GitHubOAuthState(models.Model):
    """
    Temporary storage for OAuth state parameter
    Used to prevent CSRF attacks during GitHub OAuth flow
    """
    state = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'github_oauth_states'
        verbose_name = 'GitHub OAuth State'
        verbose_name_plural = 'GitHub OAuth States'
    
    def __str__(self):
        return f"State: {self.state[:20]}..."
    
    @classmethod
    def cleanup_old_states(cls):
        """
        Remove states older than 10 minutes
        """
        from datetime import timedelta
        threshold = timezone.now() - timedelta(minutes=10)
        cls.objects.filter(created_at__lt=threshold).delete()
