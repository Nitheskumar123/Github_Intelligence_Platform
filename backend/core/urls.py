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
    path('repositories/sync/', views.sync_repositories, name='sync_repositories'),
    path('repositories/', views.list_repositories, name='list_repositories'),
]
