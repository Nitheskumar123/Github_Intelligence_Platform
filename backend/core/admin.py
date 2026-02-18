from django.contrib import admin
from .models import User, Repository, GitHubOAuthState


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'github_login', 'email', 'created_at')
    search_fields = ('username', 'github_login', 'email')
    readonly_fields = ('github_id', 'created_at', 'updated_at')


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'language', 'stars_count', 'is_active')
    search_fields = ('full_name', 'name')
    list_filter = ('is_private', 'is_fork', 'is_active', 'language')
    readonly_fields = ('github_id', 'created_at', 'updated_at')


@admin.register(GitHubOAuthState)
class GitHubOAuthStateAdmin(admin.ModelAdmin):
    list_display = ('state', 'created_at', 'is_used')
    readonly_fields = ('state', 'created_at')
