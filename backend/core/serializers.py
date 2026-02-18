from rest_framework import serializers
from .models import (
    User, Repository, PullRequest, Issue, Commit, 
    Contributor, RepositoryWebhook, WebhookEvent
)


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model
    """
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'github_id',
            'github_login',
            'github_avatar_url',
            'github_profile_url',
            'github_bio',
            'github_company',
            'github_location',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RepositorySerializer(serializers.ModelSerializer):
    """
    Serializer for Repository model
    """
    pull_requests_count = serializers.SerializerMethodField()
    issues_count = serializers.SerializerMethodField()
    commits_count = serializers.SerializerMethodField()
    contributors_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Repository
        fields = [
            'id',
            'github_id',
            'name',
            'full_name',
            'description',
            'html_url',
            'is_private',
            'is_fork',
            'language',
            'stars_count',
            'forks_count',
            'open_issues_count',
            'watchers_count',
            'default_branch',
            'size',
            'has_issues',
            'has_projects',
            'has_wiki',
            'is_active',
            'webhook_id',
            'last_synced_at',
            'created_at',
            'updated_at',
            'github_created_at',
            'github_updated_at',
            'github_pushed_at',
            'pull_requests_count',
            'issues_count',
            'commits_count',
            'contributors_count',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_pull_requests_count(self, obj):
        return obj.pull_requests.count()
    
    def get_issues_count(self, obj):
        return obj.issues.count()
    
    def get_commits_count(self, obj):
        return obj.commits.count()
    
    def get_contributors_count(self, obj):
        return obj.contributors.count()


class PullRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for PullRequest model
    """
    class Meta:
        model = PullRequest
        fields = [
            'id',
            'github_id',
            'number',
            'title',
            'body',
            'state',
            'html_url',
            'author_login',
            'author_avatar_url',
            'head_branch',
            'base_branch',
            'additions',
            'deletions',
            'changed_files',
            'comments_count',
            'review_comments_count',
            'commits_count',
            'mergeable',
            'merged',
            'merged_at',
            'closed_at',
            'created_at',
            'updated_at',
            'synced_at',
        ]


class IssueSerializer(serializers.ModelSerializer):
    """
    Serializer for Issue model
    """
    class Meta:
        model = Issue
        fields = [
            'id',
            'github_id',
            'number',
            'title',
            'body',
            'state',
            'html_url',
            'author_login',
            'author_avatar_url',
            'labels',
            'assignees',
            'comments_count',
            'closed_at',
            'created_at',
            'updated_at',
            'synced_at',
        ]


class CommitSerializer(serializers.ModelSerializer):
    """
    Serializer for Commit model
    """
    message_short = serializers.SerializerMethodField()
    
    class Meta:
        model = Commit
        fields = [
            'id',
            'sha',
            'message',
            'message_short',
            'html_url',
            'author_name',
            'author_email',
            'author_login',
            'author_avatar_url',
            'additions',
            'deletions',
            'total_changes',
            'committed_at',
            'synced_at',
        ]
    
    def get_message_short(self, obj):
        """Get first line of commit message"""
        return obj.message.split('\n')[0][:100]


class ContributorSerializer(serializers.ModelSerializer):
    """
    Serializer for Contributor model
    """
    class Meta:
        model = Contributor
        fields = [
            'id',
            'github_login',
            'avatar_url',
            'html_url',
            'contributions',
            'synced_at',
        ]


class RepositoryWebhookSerializer(serializers.ModelSerializer):
    """
    Serializer for RepositoryWebhook model
    """
    class Meta:
        model = RepositoryWebhook
        fields = [
            'id',
            'github_webhook_id',
            'webhook_url',
            'events',
            'is_active',
            'last_delivery_at',
            'total_deliveries',
            'failed_deliveries',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WebhookEventSerializer(serializers.ModelSerializer):
    """
    Serializer for WebhookEvent model
    """
    class Meta:
        model = WebhookEvent
        fields = [
            'id',
            'event_type',
            'delivery_id',
            'payload',
            'processed',
            'processed_at',
            'error_message',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']
