"""
Groq-Powered Documentation Generator
AI-powered documentation creation for GitHub repositories.
Generates READMEs, API Docs, Contributing Guidelines, and Changelogs.
"""

import time
import logging
from typing import Dict, List, Any, Optional

from django.conf import settings
from groq import Groq

logger = logging.getLogger(__name__)

class GroqDocumentationGenerator:
    """
    Generate comprehensive, markdown-formatted documentation using Groq AI.
    Analyzes repository structure, detects frameworks, and extracts context.
    """
    
    def __init__(self):
        # Initialize the synchronous Groq client
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        # Fallback to a default model if not specified in settings
        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
        self.max_tokens = 4096
        # Roughly estimate char-to-token ratio to prevent context window overflow
        self.char_limit = 15000 

    def _get_usage_tokens(self, response: Any) -> int:
        """Safely extract token usage from Groq response."""
        if hasattr(response, 'usage') and response.usage:
            return getattr(response.usage, 'total_tokens', 0)
        return 0

    def generate_readme(self, repository: Any, code_files: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generate a comprehensive README.md for the repository.
        
        Args:
            repository: Repository model instance containing metadata.
            code_files: List of dictionaries with 'path' and 'content' keys.
            
        Returns:
            dict: Generated documentation and metadata.
        """
        start_time = time.time()
        logger.info(f"Generating README for {repository.full_name}")
        
        # Analyze code structure and detect tech stack
        code_summary = self.analyze_code_structure(code_files)
        frameworks = self.detect_frameworks(code_files)
        
        system_prompt = """You are an elite open-source technical writer. 
Your task is to create a world-class, comprehensive README.md file.

The README must include:
1. A catchy project title and professional description
2. Badges (placeholders for build status, license, version)
3. Key Features (bulleted list)
4. Tech Stack details
5. Prerequisites and Installation Instructions
6. Usage Examples with code snippets
7. Project Structure breakdown
8. Contributing Guidelines (brief summary)
9. License information

Formatting Rules:
- Use clean, standard Markdown.
- Use appropriate heading hierarchies (#, ##, ###).
- Provide syntax-highlighted code blocks (```python, ```javascript, etc.).
- Make it look professional and inviting to new developers."""

        framework_str = ", ".join(frameworks) if frameworks else "Unknown/Custom"
        
        user_message = f"""Generate README.md for this repository:

**Repository Name:** {repository.full_name}
**Description:** {repository.description or 'No description provided'}
**Primary Language:** {repository.language or 'Unknown'}
**Detected Frameworks:** {framework_str}

**Repository File Structure Summary:**
{code_summary}

**Code Samples (to understand context):**
{self.format_code_samples(code_files, limit=5)}

Please generate the complete, production-ready README.md content now."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=self.max_tokens,
                temperature=0.4, # Balanced temperature for creativity + structure
            )
            
            content = response.choices[0].message.content
            
            return {
                'success': True,
                'content': content,
                'tokens_used': self._get_usage_tokens(response),
                'generation_time': time.time() - start_time
            }
            
        except Exception as e:
            logger.error(f"Error generating README with Groq: {e}")
            return {
                'success': False,
                'error': str(e),
                'tokens_used': 0,
                'generation_time': time.time() - start_time
            }

    def generate_api_documentation(self, code_files: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generate detailed API documentation by extracting public functions/endpoints.
        """
        start_time = time.time()
        logger.info("Generating API Documentation")
        
        system_prompt = """You are a meticulous API documentation specialist.
Your task is to analyze raw code and extract a clean, beautiful API Reference.

For every public API endpoint, class, or critical function found, document:
1. Endpoint / Function Name
2. Brief Description
3. Parameters / Request Body (with types if available)
4. Return Values / Response Format
5. Concrete Example Usage (Code snippet)
6. Possible Errors / Exceptions

Format everything cleanly in Markdown, using tables for parameters where appropriate."""

        # Extract only API-relevant code to save context window
        api_code = self.extract_api_code(code_files)
        
        # Prevent context window overflow
        if len(api_code) > self.char_limit:
            api_code = api_code[:self.char_limit] + "\n...[TRUNCATED due to length]..."

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze and document these APIs:\n\n{api_code}"}
                ],
                max_tokens=self.max_tokens,
                temperature=0.2, # Lower temp for strictly factual extraction
            )
            
            return {
                'success': True,
                'content': response.choices[0].message.content,
                'tokens_used': self._get_usage_tokens(response),
                'generation_time': time.time() - start_time
            }
            
        except Exception as e:
            logger.error(f"Error generating API docs with Groq: {e}")
            return {'success': False, 'error': str(e), 'tokens_used': 0, 'generation_time': time.time() - start_time}

    def generate_contributing_guide(self, repository: Any, code_files: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generate a CONTRIBUTING.md file tailored to the repository's stack.
        """
        start_time = time.time()
        frameworks = self.detect_frameworks(code_files)
        framework_str = ", ".join(frameworks) if frameworks else "standard"
        
        system_prompt = f"""You are an open-source community manager. 
Create a welcoming and comprehensive CONTRIBUTING.md guide.
Tailor the local development setup instructions for a {repository.language} project using {framework_str}.

Include sections for:
1. Welcome message
2. Code of Conduct summary
3. How to report bugs
4. How to submit feature requests
5. Local development setup (installing dependencies, running tests)
6. Pull Request process and conventions
7. Commit message guidelines"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate CONTRIBUTING.md for {repository.full_name}."}
                ],
                max_tokens=2048,
                temperature=0.5,
            )
            
            return {
                'success': True,
                'content': response.choices[0].message.content,
                'tokens_used': self._get_usage_tokens(response),
                'generation_time': time.time() - start_time
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'tokens_used': 0, 'generation_time': time.time() - start_time}

    def generate_changelog(self, commits: List[Any], repository: Any) -> Dict[str, Any]:
        """
        Generate a CHANGELOG.md based on recent commit history.
        """
        start_time = time.time()
        
        if not commits:
            return {'success': True, 'content': "No commits available to generate changelog.", 'tokens_used': 0}
            
        commit_text = "\n".join([f"- {c.sha[:7]}: {c.message} (@{c.author_login})" for c in commits[:100]])
        
        system_prompt = """You are a release manager.
Analyze the provided git commit history and organize it into a readable CHANGELOG.md format.
Categorize the changes into sections like:
- 🚀 Features
- 🐛 Bug Fixes
- 🔧 Maintenance / Refactoring
- 📖 Documentation

Ignore trivial merge commits or typos. Focus on user-facing or architectural changes."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate a changelog for {repository.full_name} from these commits:\n\n{commit_text}"}
                ],
                max_tokens=2048,
                temperature=0.3,
            )
            
            return {
                'success': True,
                'content': response.choices[0].message.content,
                'tokens_used': self._get_usage_tokens(response),
                'generation_time': time.time() - start_time
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'tokens_used': 0, 'generation_time': time.time() - start_time}

    # ==========================================
    # Helper & Analysis Methods
    # ==========================================

    def detect_frameworks(self, code_files: List[Dict[str, str]]) -> List[str]:
        """
        Scan file names to detect common frameworks and libraries to enrich the prompt.
        """
        frameworks = set()
        file_paths = [f['path'].lower() for f in code_files]
        
        for path in file_paths:
            # Python
            if 'manage.py' in path or 'wsgi.py' in path: frameworks.add('Django')
            if 'requirements.txt' in path: frameworks.add('Python/Pip')
            if 'fastapi' in path or 'main.py' in path: frameworks.add('FastAPI (Potential)')
            
            # JavaScript/Node
            if 'package.json' in path: frameworks.add('Node.js')
            if 'next.config.js' in path: frameworks.add('Next.js')
            if 'nuxt.config' in path: frameworks.add('Nuxt.js')
            if 'vue' in path and path.endswith('.vue'): frameworks.add('Vue.js')
            if 'react' in path or path.endswith('.jsx') or path.endswith('.tsx'): frameworks.add('React')
            
            # Java/Spring
            if 'pom.xml' in path: frameworks.add('Maven/Java')
            if 'build.gradle' in path: frameworks.add('Gradle')
            
            # Go/Rust/Others
            if 'go.mod' in path: frameworks.add('Go')
            if 'cargo.toml' in path: frameworks.add('Rust/Cargo')
            if 'dockerfile' in path or 'docker-compose' in path: frameworks.add('Docker')
            
        return list(frameworks)

    def analyze_code_structure(self, code_files: List[Dict[str, str]]) -> str:
        """
        Analyze repository structure and count file types.
        """
        if not code_files:
            return "No files detected."
            
        structure = []
        file_types = {}
        components = []
        
        for file_info in code_files:
            path = file_info.get('path', '')
            if not path: continue
            
            # Count extensions
            ext = path.split('.')[-1] if '.' in path else 'no-extension'
            file_types[ext] = file_types.get(ext, 0) + 1
            
            # Identify architectural components
            if any(k in path.lower() for k in ['main', 'app', 'index', 'server', 'api', 'urls', 'views', 'models']):
                components.append(path)
        
        structure.append("**File Extention Breakdown:**")
        for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:10]:
            structure.append(f"- .{ext}: {count} files")
        
        if components:
            structure.append("\n**Core Components Identified:**")
            for comp in components[:10]:
                structure.append(f"- {comp}")
                
        return "\n".join(structure)
    
    def format_code_samples(self, code_files: List[Dict[str, str]], limit: int = 3) -> str:
        """
        Format a limited number of code samples into a markdown block for the prompt context.
        Truncates large files to save tokens.
        """
        samples = []
        
        for file_info in code_files[:limit]:
            path = file_info.get('path', 'unknown_file')
            content = file_info.get('content', '')[:1200]  # Hard limit per file
            language = self.detect_language(path)
            
            samples.append(f"**File:** `{path}`")
            samples.append(f"```{language}\n{content}\n```\n")
            
        return "\n".join(samples) if samples else "No code samples available."
    
    def extract_api_code(self, code_files: List[Dict[str, str]]) -> str:
        """
        Scan files and extract segments that look like API endpoints or controllers.
        """
        api_code = []
        api_keywords = ['@app.route', '@api', 'def api_', 'class API', '/api/', 'router.', '@GetMapping', '@PostMapping', 'app.get(', 'app.post(']
        
        for file_info in code_files:
            content = file_info.get('content', '')
            path = file_info.get('path', '')
            
            # If the filename suggests an API, include more of it
            if 'api' in path.lower() or 'route' in path.lower() or 'controller' in path.lower():
                api_code.append(f"**File: {path}**")
                api_code.append(f"```\n{content[:2000]}\n```\n")
                continue
                
            # Otherwise, check content for keywords
            if any(keyword in content for keyword in api_keywords):
                api_code.append(f"**File: {path}**")
                # Grab a chunk of the file that contains the keyword
                api_code.append(f"```\n{content[:1500]}\n```\n")
        
        return "\n".join(api_code) if api_code else "No distinct API endpoints detected in provided files."
    
    def detect_language(self, filename: str) -> str:
        """
        Map file extensions to markdown language tags.
        """
        ext_map = {
            'py': 'python',
            'js': 'javascript',
            'jsx': 'jsx',
            'ts': 'typescript',
            'tsx': 'tsx',
            'java': 'java',
            'cpp': 'cpp',
            'c': 'c',
            'go': 'go',
            'rs': 'rust',
            'rb': 'ruby',
            'php': 'php',
            'html': 'html',
            'css': 'css',
            'json': 'json',
            'yml': 'yaml',
            'yaml': 'yaml',
            'sh': 'bash',
            'md': 'markdown'
        }
        
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        return ext_map.get(ext, 'text')