import time
import json
import logging
from typing import Dict, Any, Optional
from django.conf import settings
from groq import AsyncGroq

logger = logging.getLogger(__name__)

class AsyncGroqCodeAnalyzer:
    """
    Analyze code using Groq AI (Llama 3, Mixtral, etc.)
    Designed to process PR diffs and raw code for security, performance, and quality.
    """
    
    def __init__(self):
        # Initialize the AsyncGroq client using Django settings
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        # Fallback to a default model if not specified in settings
        self.model = getattr(settings, 'GROQ_MODEL', 'llama3-70b-8192')
        self.max_tokens = getattr(settings, 'GROQ_MAX_TOKENS', 4096)

    def _extract_json_from_response(self, content: str) -> Dict[str, Any]:
        """
        Helper method to reliably extract JSON from LLM responses.
        Handles cases where the model wraps the output in markdown blocks.
        """
        try:
            # First, try to parse it directly
            return json.loads(content)
        except json.JSONDecodeError:
            # If direct parsing fails, look for markdown JSON blocks
            try:
                if '```json' in content:
                    json_start = content.find('```json') + 7
                    json_end = content.find('```', json_start)
                    json_str = content[json_start:json_end].strip()
                    return json.loads(json_str)
                elif '{' in content:
                    # Fallback: find the first '{' and last '}'
                    json_start = content.find('{')
                    json_end = content.rfind('}') + 1
                    json_str = content[json_start:json_end].strip()
                    return json.loads(json_str)
            except Exception as e:
                logger.error(f"Failed to extract JSON from response: {e}")
        
        # Return an empty dict if all parsing fails
        return {}

    async def analyze_pr_diff(self, diff_content: str, pr_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a pull request diff for issues asynchronously using Groq.
        
        Args:
            diff_content (str): The raw Git diff content.
            pr_context (dict): PR metadata (title, description, files changed).
        
        Returns:
            dict: Analysis results including issues, performance hits, and suggestions.
        """
        start_time = time.time()
        
        system_prompt = """You are an expert code reviewer analyzing a pull request.

Your task is to:
1. Identify security vulnerabilities
2. Find performance issues
3. Detect code smells and bad practices
4. Highlight positive aspects
5. Suggest improvements

You MUST respond in valid JSON format with this exact structure:
{
    "summary": "Brief overall assessment",
    "security_issues": [
        {
            "severity": "high|medium|low",
            "line": 45,
            "issue": "Description of issue",
            "recommendation": "How to fix"
        }
    ],
    "performance_issues": [],
    "code_smells": [],
    "positive_points": ["Good things about this PR"],
    "complexity_score": 15,
    "estimated_review_time": "15 minutes"
}

Be specific about line numbers and provide actionable recommendations."""

        user_message = f"""Analyze this pull request:

**PR Title:** {pr_context.get('title', 'N/A')}
**Description:** {pr_context.get('description', 'No description')}
**Files Changed:** {pr_context.get('files_changed', 0)}
**Additions:** +{pr_context.get('additions', 0)} lines
**Deletions:** -{pr_context.get('deletions', 0)} lines

**Diff:**
{diff_content[:15000]}  # Limited to prevent exceeding context window
Provide detailed analysis in JSON format."""

        try:
            # Groq expects the system prompt to be part of the messages array
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0.2, # Lower temperature for more analytical/consistent outputs
                response_format={"type": "json_object"} # Forces Groq to return valid JSON
            )
            
            content = response.choices[0].message.content
            
            # Extract tokens (Groq uses standard OpenAI usage tracking style)
            tokens_used = 0
            if hasattr(response, 'usage') and response.usage:
                tokens_used = response.usage.total_tokens
                
            analysis_time = time.time() - start_time
            
            # Parse the JSON response
            analysis = self._extract_json_from_response(content)
            
            return {
                'success': True,
                'analysis': analysis,
                'tokens_used': tokens_used,
                'analysis_time': analysis_time
            }
            
        except Exception as e:
            logger.error(f"Error analyzing PR with Groq: {e}")
            return {
                'success': False,
                'error': str(e),
                'tokens_used': 0,
                'analysis_time': time.time() - start_time
            }
    
    async def analyze_code_quality(self, code_content: str, language: str = 'python') -> Dict[str, Any]:
        """
        Analyze raw code quality and complexity asynchronously.
        
        Args:
            code_content (str): The source code to analyze.
            language (str): Programming language for context.
        
        Returns:
            dict: Quality analysis including score, issues, and suggestions.
        """
        system_prompt = f"""You are a strict code quality expert analyzing {language} code.

Evaluate the code on the following criteria:
1. Code readability and clean code principles
2. Maintainability and architecture
3. Following standard best practices for {language}
4. Potential edge-case bugs
5. Documentation and typing quality

You MUST respond in valid JSON format exactly like this:
{{
    "quality_score": 85,
    "readability": "Good|Average|Poor",
    "issues": ["List of specific issues found"],
    "suggestions": ["Specific improvement suggestions"]
}}"""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this {language} code:\n\n```{language}\n{code_content[:8000]}\n```"}
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=2048,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            
            # Parse the returned content safely
            analysis = self._extract_json_from_response(content)
            
            # Fallback if parsing returned empty
            if not analysis:
                return {'quality_score': 70, 'issues': ['Failed to parse AI response'], 'suggestions': []}
                
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing code quality with Groq: {e}")
            return {
                'quality_score': 0, 
                'issues': [f'API Error: {str(e)}'], 
                'suggestions': []
            }
    
    def generate_pr_comment(self, analysis: Dict[str, Any]) -> str:
        """
        Generate a formatted Markdown comment for a Pull Request based on the AI analysis.
        This method is synchronous as it does not make any API calls.
        
        Args:
            analysis (dict): Analysis results dictionary returned from analyze_pr_diff.
        
        Returns:
            str: A formatted Markdown string ready to be posted to GitHub/GitLab.
        """
        comment = "🤖 **AI Code Review (Powered by Groq)**\n\n"
        
        # Summary
        comment += f"**Summary:** {analysis.get('summary', 'Analysis completed but no summary provided.')}\n\n"
        
        # Security issues
        security_issues = analysis.get('security_issues', [])
        if security_issues:
            comment += "### ⚠️ Security Vulnerabilities\n\n"
            for issue in security_issues[:5]:  # Limit to top 5 most critical
                severity = issue.get('severity', 'medium').upper()
                line = issue.get('line', 'N/A')
                description = issue.get('issue', 'Unknown issue')
                recommendation = issue.get('recommendation', 'No recommendation provided')
                
                # Emphasize high severity issues
                if severity == 'HIGH':
                    comment += f"**🚨 {severity} - Line {line}**\n"
                else:
                    comment += f"**{severity} - Line {line}**\n"
                    
                comment += f"- **Issue:** {description}\n"
                comment += f"- **Fix:** {recommendation}\n\n"
        else:
            comment += "### 🛡️ Security\n\n- No obvious security vulnerabilities detected.\n\n"
        
        # Performance issues
        perf_issues = analysis.get('performance_issues', [])
        if perf_issues:
            comment += "### 🚀 Performance Optimizations\n\n"
            for issue in perf_issues[:5]:
                severity = issue.get('severity', 'medium').upper()
                line = issue.get('line', 'N/A')
                description = issue.get('issue', 'Unknown performance issue')
                recommendation = issue.get('recommendation', 'No recommendation')
                
                comment += f"**{severity} - Line {line}**\n"
                comment += f"- **Issue:** {description}\n"
                comment += f"- **Suggestion:** {recommendation}\n\n"
        
        # Code smells / Quality issues
        code_smells = analysis.get('code_smells', [])
        if code_smells:
            comment += "### 💡 Code Quality & Smells\n\n"
            for smell in code_smells[:5]:
                issue_text = smell if isinstance(smell, str) else smell.get('issue', 'Unknown code smell')
                line_text = "" if isinstance(smell, str) else f" (Line {smell.get('line', 'N/A')})"
                comment += f"- {issue_text}{line_text}\n"
            comment += "\n"
        
        # Positive points
        positive = analysis.get('positive_points', [])
        if positive:
            comment += "### ✅ Positive Points\n\n"
            for point in positive:
                comment += f"- {point}\n"
            comment += "\n"
        
        # Summary statistics
        comment += "### 📊 Metadata\n\n"
        comment += f"- **Complexity Score:** {analysis.get('complexity_score', 'N/A')}/100\n"
        comment += f"- **Estimated Review Time:** {analysis.get('estimated_review_time', 'N/A')}\n"
        
        # Footer
        comment += "\n---\n"
        comment += "*This review was generated automatically by Groq AI. Please use your judgment when addressing these suggestions as AI can sometimes produce false positives.*"
        
        return comment