from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Health check
    path('health/', views.health_check, name='health_check'),
    
    # GitHub OAuth
    path('auth/github/', views.github_login, name='github_login'),
    path('auth/github/callback/', views.github_callback, name='github_callback'),
    
    # User APIs
    path('user/me/', views.current_user, name='current_user'),
    path('auth/logout/', views.logout_user, name='logout'),
    
    # Repository APIs
    path('repositories/', views.list_repositories, name='list_repositories'),
    path('repositories/sync/', views.sync_repositories, name='sync_repositories'),
    path('repositories/<int:repo_id>/', views.repository_detail, name='repository_detail'),
    path('repositories/<int:repo_id>/sync/', views.sync_single_repository, name='sync_single_repository'),
    
    # Pull Request APIs
    path('repositories/<int:repo_id>/pulls/', views.list_pull_requests, name='list_pull_requests'),
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/', views.pull_request_detail, name='pull_request_detail'),
    
    # Issue APIs
    path('repositories/<int:repo_id>/issues/', views.list_issues, name='list_issues'),
    path('repositories/<int:repo_id>/issues/<int:issue_number>/', views.issue_detail, name='issue_detail'),
    
    # Commit APIs
    path('repositories/<int:repo_id>/commits/', views.list_commits, name='list_commits'),
    
    # Contributor APIs
    path('repositories/<int:repo_id>/contributors/', views.list_contributors, name='list_contributors'),
    
    # Language Stats
    path('repositories/<int:repo_id>/languages/', views.repository_languages, name='repository_languages'),
    
    # Activity Feed
    path('repositories/<int:repo_id>/activity/', views.repository_activity, name='repository_activity'),
    
    # Webhook APIs
    path('repositories/<int:repo_id>/webhook/', views.setup_webhook, name='setup_webhook'),
    path('repositories/<int:repo_id>/webhook/status/', views.webhook_status, name='webhook_status'),
    path('webhooks/github/', views.github_webhook_receiver, name='github_webhook_receiver'),
    
    # Chat APIs
    path('conversations/', views.list_conversations, name='list_conversations'),
    path('conversations/create/', views.create_conversation, name='create_conversation'),
    path('conversations/<int:conversation_id>/', views.conversation_detail, name='conversation_detail'),
    path('conversations/<int:conversation_id>/delete/', views.delete_conversation, name='delete_conversation'),
    # ... (keep all existing URLs)

# Code Analysis APIs
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/analyze/', views.analyze_pr, name='analyze_pr'),
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/analysis/', views.get_pr_analysis, name='get_pr_analysis'),
    path('repositories/<int:repo_id>/documentation/generate/', views.generate_documentation, name='generate_documentation'),
    path('repositories/<int:repo_id>/documentation/', views.get_documentation, name='get_documentation'),
    path('insights/', views.get_insights, name='get_insights'),
    path('repositories/<int:repo_id>/insights/', views.get_repository_insights, name='get_repository_insights'),
    path('repositories/<int:repo_id>/insights/generate/', views.generate_insights, name='generate_insights'),
    path('insights/<int:insight_id>/resolve/', views.resolve_insight, name='resolve_insight'),
    # After the insights line, ADD:
path('insights/generate/', views.generate_insights_all, name='generate_insights_all'),
]
