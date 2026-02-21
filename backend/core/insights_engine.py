"""
Groq-Powered Insights Engine
Generates proactive AI insights about GitHub repositories using Groq (Llama-3, etc.)
Analyzes PR velocity, issue trends, and codebase activity.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from groq import Groq

from .models import Repository, CodeInsight, PullRequest, Issue, Commit

logger = logging.getLogger(__name__)

class GroqInsightsEngine:
    """
    Generate proactive, actionable insights about repositories using Groq AI.
    Analyzes activity, identifies bottlenecks, and suggests improvements.
    """
    
    def __init__(self):
        # Initialize the synchronous Groq client
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        # Fallback to a default versatile model if not specified in settings
        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
    
    def _extract_json_from_response(self, content: str) -> Dict[str, Any]:
        """
        Helper method to reliably extract JSON from LLM responses.
        Handles cases where the model wraps the output in markdown blocks.
        
        Args:
            content (str): Raw string output from the LLM.
            
        Returns:
            Dict[str, Any]: Parsed JSON dictionary.
        """
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            try:
                if '```json' in content:
                    json_start = content.find('```json') + 7
                    json_end = content.find('```', json_start)
                    json_str = content[json_start:json_end].strip()
                    return json.loads(json_str)
                elif '{' in content:
                    json_start = content.find('{')
                    json_end = content.rfind('}') + 1
                    json_str = content[json_start:json_end].strip()
                    return json.loads(json_str)
            except Exception as e:
                logger.error(f"Failed to extract JSON from Groq response: {e}")
        
        return {"insights": []}

    def generate_repository_insights(self, repository: Repository) -> List[CodeInsight]:
        """
        Main entry point to generate insights for a specific repository.
        
        Args:
            repository (Repository): The repository to analyze.
        
        Returns:
            List[CodeInsight]: A list of saved CodeInsight model instances.
        """
        logger.info(f"Generating Groq AI insights for {repository.full_name}")
        
        try:
            # 1. Collect rich repository metrics and data
            repo_data = self.collect_repository_data(repository)
            
            # 2. Generate insights using Groq
            insights_data = self.analyze_with_ai(repository, repo_data)
            
            # 3. Save generated insights to the database
            saved_insights = self.save_insights(repository, insights_data)
            
            # 4. Clean up stale/old insights
            self.cleanup_stale_insights(repository)
            
            logger.info(f"Successfully generated {len(saved_insights)} insights for {repository.full_name}")
            return saved_insights
            
        except Exception as e:
            logger.error(f"Critical failure generating insights for {repository.full_name}: {e}")
            return []
    
    def collect_repository_data(self, repository: Repository) -> Dict[str, Any]:
        """
        Collect comprehensive data about the repository for AI analysis.
        Includes activity metrics, PR velocity, and issue trends.
        
        Args:
            repository (Repository): Repository object to gather data for.
        
        Returns:
            dict: Structured repository data and metrics.
        """
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        # Pull Requests Analysis
        open_prs = repository.pull_requests.filter(state='open')
        old_prs = open_prs.filter(created_at__lt=week_ago)
        recent_merged_prs = repository.pull_requests.filter(state='closed', merged=True, merged_at__gte=month_ago)
        
        # Calculate PR Velocity (Average days to merge)
        avg_merge_time_days = None
        if recent_merged_prs.exists():
            total_merge_time = sum(
                (pr.merged_at - pr.created_at).total_seconds() 
                for pr in recent_merged_prs if pr.merged_at and pr.created_at
            )
            avg_merge_time_days = round((total_merge_time / recent_merged_prs.count()) / 86400, 1)
        
        # Issues Analysis
        open_issues = repository.issues.filter(state='open')
        critical_issues = [
            issue for issue in open_issues 
            if any(label.get('name', '').lower() in ['critical', 'urgent', 'bug', 'security'] 
                   for label in issue.labels)
        ]
        
        # Commit Analysis
        recent_commits = repository.commits.filter(committed_at__gte=week_ago)
        last_commit = repository.commits.first()
        days_since_commit = (now - last_commit.committed_at).days if last_commit else None
        
        # Calculate Developer Activity
        active_contributors = set(commit.author_login for commit in recent_commits if commit.author_login)
        
        return {
            # PR Metrics
            'open_prs_count': open_prs.count(),
            'old_prs_count': old_prs.count(),
            'recent_merged_prs_count': recent_merged_prs.count(),
            'avg_merge_time_days': avg_merge_time_days,
            'old_prs': list(old_prs[:5].values('number', 'title', 'created_at', 'author_login')),
            
            # Issue Metrics
            'open_issues_count': open_issues.count(),
            'critical_issues_count': len(critical_issues),
            'critical_issues': [
                {'number': issue.number, 'title': issue.title, 'labels': issue.labels}
                for issue in critical_issues[:5]
            ],
            
            # Commit & Activity Metrics
            'recent_commits_count': recent_commits.count(),
            'days_since_commit': days_since_commit,
            'active_contributors_count': len(active_contributors),
            
            # Repo Meta
            'stars': repository.stars_count,
            'forks': repository.forks_count,
            'language': repository.language,
            'last_synced': repository.last_synced_at,
        }
    
    def analyze_with_ai(self, repository: Repository, repo_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Use Groq AI to analyze repository data and generate proactive insights.
        
        Args:
            repository (Repository): The repository being analyzed.
            repo_data (dict): Dictionary of collected metrics.
        
        Returns:
            list: Parsed JSON array of insight dictionaries.
        """
        system_prompt = """You are an elite, proactive GitHub repository manager and AI assistant.

Analyze the provided repository metrics and generate highly actionable, insightful observations.
Focus on identifying bottlenecks, celebrating good practices, and finding security/quality risks.

Generate insights in these categories:
1. **Alerts** - Urgent issues (e.g., critical bugs, stale PRs blocking development).
2. **Suggestions** - Process or code improvements (e.g., PR velocity is slow).
3. **Wins** - Positive trends (e.g., fast merge times, high activity).
4. **Trends** - Broader patterns over the last 7-30 days.

You MUST respond in strictly valid JSON format matching this exact schema:
{
    "insights": [
        {
            "type": "alert|suggestion|win|trend",
            "priority": "critical|high|medium|low",
            "title": "Short, clear title (max 60 chars)",
            "description": "Brief description of the issue or trend (max 200 chars)",
            "category": "security|performance|quality|activity|community",
            "recommendation": "Specific, actionable step to take next"
        }
    ]
}

Focus strictly on the provided data. Do not hallucinate metrics. Be highly specific."""

        user_message = f"""Analyze this repository and generate insights based on the current data:

**Repository Metadata:**
- Name: {repository.full_name}
- Primary Language: {repo_data['language']}
- Stars: {repo_data['stars']} | Forks: {repo_data['forks']}

**Current Pipeline Status:**
- Total Open PRs: {repo_data['open_prs_count']}
- Stale PRs (>7 days old): {repo_data['old_prs_count']}
- Average Merge Time (30 days): {repo_data.get('avg_merge_time_days', 'N/A')} days
- Active Contributors (7 days): {repo_data['active_contributors_count']}

**Issue Tracker:**
- Total Open Issues: {repo_data['open_issues_count']}
- Critical/Urgent Issues: {repo_data['critical_issues_count']}

**Recent Activity:**
- Commits in last 7 days: {repo_data['recent_commits_count']}
- Days Since Last Commit: {repo_data['days_since_commit']}

**Details of Stale Pull Requests:**
{self.format_prs(repo_data.get('old_prs', []))}

**Details of Critical Issues:**
{self.format_issues(repo_data.get('critical_issues', []))}

Generate up to 5 specific, actionable insights in valid JSON format."""

        try:
            # Groq expects system prompts inside the messages array
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=2048,
                temperature=0.3, # Low temperature for consistent JSON output
                response_format={"type": "json_object"} # Force Groq to output JSON
            )
            
            content = response.choices[0].message.content
            
            # Parse the JSON response safely
            parsed_data = self._extract_json_from_response(content)
            return parsed_data.get('insights', [])
            
        except Exception as e:
            logger.error(f"Groq API Error generating insights: {e}")
            return []
    
    def save_insights(self, repository: Repository, insights: List[Dict[str, Any]]) -> List[CodeInsight]:
        """
        Save or update generated insights in the database.
        
        Args:
            repository (Repository): The repository these insights belong to.
            insights (list): List of insight dictionaries from the AI.
        
        Returns:
            list: Saved CodeInsight Django model instances.
        """
        saved_insights = []
        
        for insight_data in insights:
            # Skip invalid insights missing required fields
            if not insight_data.get('title') or not insight_data.get('type'):
                continue
                
            # Check if a very similar insight already exists and is unresolved
            existing = CodeInsight.objects.filter(
                repository=repository,
                title=insight_data.get('title', ''),
                is_resolved=False
            ).first()
            
            if existing:
                # Update existing insight with fresh data
                existing.description = insight_data.get('description', existing.description)
                existing.recommendation = insight_data.get('recommendation', existing.recommendation)
                existing.priority = insight_data.get('priority', existing.priority)
                existing.updated_at = timezone.now()
                existing.save()
                saved_insights.append(existing)
            else:
                # Create a brand new insight
                new_insight = CodeInsight.objects.create(
                    repository=repository,
                    insight_type=insight_data.get('type', 'suggestion').lower(),
                    priority=insight_data.get('priority', 'medium').lower(),
                    title=insight_data.get('title', 'Untitled Insight')[:255],
                    description=insight_data.get('description', ''),
                    recommendation=insight_data.get('recommendation', ''),
                    category=insight_data.get('category', 'general').lower()
                )
                saved_insights.append(new_insight)
        
        return saved_insights
        
    def cleanup_stale_insights(self, repository: Repository) -> None:
        """
        Automatically resolve older insights that are likely no longer relevant.
        For example, trends from a month ago should not clutter the dashboard.
        """
        stale_threshold = timezone.now() - timedelta(days=14)
        
        # Find insights older than 14 days that are still marked unresolved
        stale_insights = CodeInsight.objects.filter(
            repository=repository,
            is_resolved=False,
            created_at__lt=stale_threshold
        )
        
        # Mark them as resolved automatically
        count = stale_insights.update(
            is_resolved=True, 
            resolved_at=timezone.now(),
            recommendation="Auto-resolved due to age. Issue may have passed or been fixed."
        )
        
        if count > 0:
            logger.info(f"Auto-resolved {count} stale insights for {repository.full_name}")

    def format_prs(self, prs: List[Dict[str, Any]]) -> str:
        """
        Format Pull Request dictionaries into a readable string for the LLM prompt.
        """
        if not prs:
            return "No stale Pull Requests found."
        
        lines = []
        for pr in prs:
            created_date = pr['created_at'].strftime("%Y-%m-%d") if isinstance(pr['created_at'], timezone.datetime) else pr['created_at']
            lines.append(f"- PR #{pr['number']}: '{pr['title']}' (Author: @{pr['author_login']}, Opened: {created_date})")
        
        return "\n".join(lines)
    
    def format_issues(self, issues: List[Dict[str, Any]]) -> str:
        """
        Format Issue dictionaries into a readable string for the LLM prompt.
        """
        if not issues:
            return "No critical open Issues found."
        
        lines = []
        for issue in issues:
            labels = ', '.join([label.get('name', 'Unknown') for label in issue.get('labels', [])])
            lines.append(f"- Issue #{issue['number']}: '{issue['title']}' [Labels: {labels}]")
        
        return "\n".join(lines)
    
    def generate_all_insights(self, user) -> int:
        """
        Generate insights for all active repositories belonging to a specific user.
        Usually called by a periodic background Celery task.
        
        Args:
            user (User): Django User object.
        
        Returns:
            int: Total number of insights generated across all repositories.
        """
        repositories = Repository.objects.filter(user=user, is_active=True)
        total_insights = 0
        
        logger.info(f"Starting bulk insight generation for user {user.username} ({repositories.count()} repos)")
        
        for repo in repositories:
            try:
                insights = self.generate_repository_insights(repo)
                total_insights += len(insights)
            except Exception as e:
                logger.error(f"Failed to generate insights for {repo.full_name} during bulk run: {e}")
                continue
        
        return total_insights