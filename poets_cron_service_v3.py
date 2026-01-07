#!/usr/bin/env python3
"""
Poets Generator Service v3.1 - Fixed Resource Usage
Enhanced with efficient queue processing - NO GPU usage when queue is empty
"""

import os
import sys
import json
import logging
import time
import argparse
import requests
import autogen
import sqlite3
import fcntl
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from media import AudioPipeline, ImagePipeline
from media.base import MediaArtifact
from media.utils import MediaPipelineError

# Import tools from local directory first, fallback to API directory
try:
    # Try local tools.py first (in poets-cron-service directory)
    from tools import (
        save_text_to_file, 
        save_to_sqlite_database, 
        query_database_content, 
        get_database_stats,
        tavily_research_assistant
    )
    print("✅ Successfully imported tools from local directory")
except ImportError as e:
    print(f"⚠️ Local tools import failed: {e}")
    # Fallback to API directory
    sys.path.append('/Volumes/Tikbalang2TB/Users/tikbalang/anthonys-musings-api')
    try:
        from tools import (
            save_text_to_file, 
            save_to_sqlite_database, 
            query_database_content, 
            get_database_stats,
            tavily_research_assistant
        )
        print("✅ Successfully imported tools from API directory (fallback)")
    except ImportError as e2:
        print(f"❌ ERROR: Could not import tools from either location:")
        print(f"   Local: {e}")
        print(f"   API: {e2}")
        print("Make sure tools.py exists in current directory or API directory")
        sys.exit(1)


class ProcessLock:
    """Simple file-based process lock to prevent concurrent executions"""
    
    def __init__(self, lock_file: str, timeout_minutes: int = 60):
        self.lock_file = lock_file
        self.timeout_minutes = timeout_minutes
        self.lock_fd = None
        
    def acquire(self) -> bool:
        """Attempt to acquire the lock"""
        try:
            # Check for stale lock files
            self._cleanup_stale_lock()
            
            # Try to create and lock the file
            self.lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_WRONLY | os.O_EXCL)
            
            # Write process info
            lock_info = {
                "pid": os.getpid(),
                "started_at": datetime.now().isoformat(),
                "timeout_at": (datetime.now() + timedelta(minutes=self.timeout_minutes)).isoformat()
            }
            os.write(self.lock_fd, json.dumps(lock_info).encode())
            os.fsync(self.lock_fd)
            
            return True
            
        except FileExistsError:
            # Lock file exists - another process is running
            return False
        except Exception as e:
            print(f"Error acquiring lock: {e}")
            return False
    
    def release(self):
        """Release the lock"""
        try:
            if self.lock_fd is not None:
                os.close(self.lock_fd)
                self.lock_fd = None
            
            if os.path.exists(self.lock_file):
                os.unlink(self.lock_file)
                
        except Exception as e:
            print(f"Error releasing lock: {e}")
    
    def _cleanup_stale_lock(self):
        """Remove stale lock files from crashed processes"""
        if not os.path.exists(self.lock_file):
            return
            
        try:
            with open(self.lock_file, 'r') as f:
                lock_info = json.load(f)
            
            timeout_str = lock_info.get('timeout_at')
            if timeout_str:
                timeout_time = datetime.fromisoformat(timeout_str)
                if datetime.now() > timeout_time:
                    # Lock is stale, remove it
                    os.unlink(self.lock_file)
                    print(f"Removed stale lock file (timed out)")
                    
        except Exception as e:
            # If we can't read the lock file, assume it's corrupt and remove it
            try:
                os.unlink(self.lock_file)
                print(f"Removed corrupt lock file")
            except:
                pass
    
    def __enter__(self):
        """Context manager entry"""
        if not self.acquire():
            raise RuntimeError("Could not acquire process lock - another generation may be running")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release()


class PoetsService:
    """Main service class for automated content generation"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self.load_config()
        self.setup_logging()
        self.logger = logging.getLogger(__name__)
        self.lock_file = os.path.join(os.path.dirname(config_path), "poets_generation.lock")
        self.media_config = self.config.get('media', {})
        self.media_enabled = bool(self.media_config.get('enabled'))
        self.media_output_root: Optional[Path] = None
        self.media_pipelines: Dict[str, Any] = {}
        self.media_prompt_type_map: Dict[str, str] = {}
        self.media_available = False

        if self.media_enabled:
            try:
                self._initialize_media_support()
            except Exception as exc:
                self.logger.error(f"Media pipeline initialization failed: {exc}")
                self.media_enabled = False
        
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"ERROR: Failed to load config from {self.config_path}: {e}")
            sys.exit(1)
            
    def setup_logging(self):
        """Setup logging configuration"""
        log_config = self.config.get('logging', {})
        log_file = log_config.get('file', 'logs/poets_cron.log')
        log_level = getattr(logging, log_config.get('level', 'INFO'))
        
        # Create logs directory if it doesn't exist
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )

    def _initialize_media_support(self):
        """Instantiate media pipelines and ensure database schema."""
        config_dir = Path(self.config_path).parent.resolve()
        comfy_config = self.media_config.get('comfyui', {})
        scripts = self.media_config.get('scripts', {})
        script_args_config = self.media_config.get('script_args', {})

        output_directory = comfy_config.get('output_directory', 'GeneratedMedia')
        self.media_output_root = (config_dir / output_directory).resolve()
        self.media_output_root.mkdir(parents=True, exist_ok=True)
        for subdir in ('image', 'audio'):
            (self.media_output_root / subdir).mkdir(parents=True, exist_ok=True)

        python_executable = comfy_config.get('python') or sys.executable
        queue_size = int(comfy_config.get('queue_size', 1))
        timeout_seconds = int(comfy_config.get('timeout_seconds', 600))
        comfyui_directory = comfy_config.get('comfyui_directory')

        pipelines: Dict[str, Any] = {}
        script_definitions = {
            'image': ('image', ImagePipeline),
            'music': ('audio', AudioPipeline),
            'audio': ('audio', AudioPipeline),
        }

        for script_key, (artifact_type, pipeline_cls) in script_definitions.items():
            script_rel_path = scripts.get(script_key)
            if not script_rel_path:
                continue

            script_path = (config_dir / script_rel_path).resolve()
            if not script_path.exists():
                self.logger.error(
                    f"Media script for '{script_key}' prompts not found at {script_path}"
                )
                continue

            if artifact_type in pipelines:
                # Already configured (e.g., both 'music' and 'audio' entries)
                continue

            raw_extra_args = script_args_config.get(script_key, [])
            if isinstance(raw_extra_args, str):
                extra_args = [raw_extra_args]
            else:
                extra_args = list(raw_extra_args or [])
            pipelines[artifact_type] = pipeline_cls(
                script_path=script_path,
                python_executable=python_executable,
                output_root=self.media_output_root,
                queue_size=queue_size,
                timeout_seconds=timeout_seconds,
                comfyui_directory=comfyui_directory,
                extra_args=extra_args,
            )

        self.media_pipelines = pipelines

        default_map = {
            'image': 'image',
            'music': 'audio',
            'audio': 'audio',
            'voice': 'audio',
        }
        configured_map = {
            key.lower(): value
            for key, value in self.media_config.get('prompt_type_map', {}).items()
        }
        default_map.update(configured_map)
        self.media_prompt_type_map = default_map

        if not self.media_pipelines:
            self.logger.warning(
                "Media processing is enabled but no pipelines were initialised. "
                "Media prompts will be skipped."
            )
            self.media_available = False
            return

        try:
            self.ensure_media_schema()
        except Exception:
            # Schema initialisation already logged; disable media support for this run.
            self.media_available = False
            return

        # Perform a lightweight health check; if it fails we log but continue gracefully.
        if self._check_comfyui_health():
            self.media_available = True
        else:
            self.logger.warning(
                "ComfyUI health check failed; media prompts will be deferred until the "
                "service detects the server is reachable."
            )
            self.media_available = False

    def get_database_connection(self):
        """Get database connection"""
        db_path = self.config['database']['path']
        return sqlite3.connect(db_path)

    def ensure_media_schema(self):
        """Ensure database tables and columns required for media artifacts exist."""
        if not self.media_enabled:
            return

        conn = None
        try:
            conn = self.get_database_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_id INTEGER NOT NULL,
                    artifact_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    preview_path TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
                )
                """
            )

            cursor.execute("PRAGMA table_info('prompts')")
            existing_columns = {row[1] for row in cursor.fetchall()}

            if 'artifact_status' not in existing_columns:
                cursor.execute(
                    "ALTER TABLE prompts ADD COLUMN artifact_status TEXT DEFAULT 'pending'"
                )

            if 'artifact_metadata' not in existing_columns:
                cursor.execute(
                    "ALTER TABLE prompts ADD COLUMN artifact_metadata TEXT"
                )

            conn.commit()
        except Exception as exc:
            self.logger.error(f"Failed to ensure media schema: {exc}")
            raise
        finally:
            if conn is not None:
                conn.close()

    def record_prompt_artifacts(self, prompt_id: int, artifacts: List[MediaArtifact]):
        """Persist generated artifact metadata to the database."""
        if not artifacts:
            return

        conn = None
        try:
            conn = self.get_database_connection()
            cursor = conn.cursor()
            rows = [
                (
                    prompt_id,
                    artifact.artifact_type,
                    artifact.file_path,
                    artifact.preview_path,
                    json.dumps(artifact.metadata) if artifact.metadata else None,
                )
                for artifact in artifacts
            ]
            cursor.executemany(
                """
                INSERT INTO prompt_artifacts (
                    prompt_id,
                    artifact_type,
                    file_path,
                    preview_path,
                    metadata
                ) VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        except Exception as exc:
            self.logger.error(f"Failed to record prompt artifacts: {exc}")
            raise
        finally:
            if conn is not None:
                conn.close()

    def _check_comfyui_health(self) -> bool:
        """Perform a lightweight health check against the configured ComfyUI host."""
        comfy_config = self.media_config.get('comfyui', {})
        host = comfy_config.get('host')
        if not host:
            return True

        host = host.rstrip('/')
        health_url = f"{host}/system_stats"
        try:
            response = requests.get(health_url, timeout=5)
            return response.status_code == 200
        except Exception as exc:
            self.logger.debug(f"ComfyUI health check error: {exc}")
            return False

    def get_unprocessed_prompts(self) -> List[Dict]:
        """Get unprocessed prompts from the database queue"""
        try:
            conn = self.get_database_connection()
            cursor = conn.cursor()
            
            # Check if prompts table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='prompts'
            """)
            
            if not cursor.fetchone():
                self.logger.info("No prompts table found - creating it")
                self.create_prompts_table(cursor)
                conn.commit()
                conn.close()
                return []
            
            # Get unprocessed prompts ordered by priority and creation time
            cursor.execute("""
                SELECT id, prompt_text, prompt_type, priority, metadata, created_at
                FROM prompts 
                WHERE status = 'unprocessed'
                ORDER BY priority ASC, created_at ASC
                LIMIT 5
            """)
            
            prompts = []
            for row in cursor.fetchall():
                metadata = json.loads(row[4]) if row[4] else {}
                prompts.append({
                    'id': row[0],
                    'prompt_text': row[1],
                    'prompt_type': row[2],
                    'priority': row[3],
                    'metadata': metadata,
                    'created_at': row[5]
                })
            
            conn.close()
            return prompts
            
        except Exception as e:
            self.logger.error(f"Error getting unprocessed prompts: {e}")
            return []

    def create_prompts_table(self, cursor):
        """Create the prompts table if it doesn't exist"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_text TEXT NOT NULL,
                prompt_type TEXT DEFAULT 'text',
                status TEXT DEFAULT 'unprocessed',
                priority INTEGER DEFAULT 5,
                config_name TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                completed_at TIMESTAMP,
                output_reference INTEGER,
                error_message TEXT,
                processing_duration INTEGER
            )
        """)

    def update_prompt_status(
        self,
        prompt_id: int,
        status: str,
        error_message: Optional[str] = None,
        *,
        artifact_status: Optional[str] = None,
        artifact_metadata: Optional[Dict[str, Any]] = None,
    ):
        """Update the status of a prompt in the database"""
        try:
            conn = self.get_database_connection()
            cursor = conn.cursor()
            
            now = datetime.now().isoformat()

            updates: Dict[str, Any] = {"status": status}

            if status == 'processing':
                updates['processed_at'] = now
            elif status in ('completed', 'failed'):
                updates['completed_at'] = now

            if error_message is not None:
                updates['error_message'] = error_message
            elif status != 'failed':
                # Clear previous error messages when transitioning out of failure
                updates['error_message'] = None

            if artifact_status is not None:
                updates['artifact_status'] = artifact_status

            if artifact_metadata is not None:
                updates['artifact_metadata'] = json.dumps(artifact_metadata)

            assignments = ", ".join(f"{column} = ?" for column in updates)
            values = list(updates.values())
            values.append(prompt_id)

            cursor.execute(
                f"UPDATE prompts SET {assignments} WHERE id = ?",
                values,
            )
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error updating prompt status: {e}")
        
    def check_environment(self) -> bool:
        """Check required environment variables"""
        required_vars = self.config.get('environment', {}).get('required_vars', [])
        
        # Add TVLY_API_KEY to required vars for Tavily functionality
        if 'TVLY_API_KEY' not in required_vars:
            required_vars.append('TVLY_API_KEY')
        
        missing_vars = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
                
        if missing_vars:
            self.logger.error(f"Missing required environment variables: {missing_vars}")
            self.logger.error("Note: TVLY_API_KEY is required for web research functionality")
            return False
            
        # Log successful environment check
        self.logger.info(f"Environment check passed: {len(required_vars)} variables found")
        return True
        
    def get_base_url(self, backend_type: str) -> Optional[str]:
        """Get base URL for specified backend type"""
        if backend_type == 'lms':
            return os.getenv("NGROKURL")
        elif backend_type == 'oll':
            return os.getenv("WIFI_LLM_URL")
        else:
            manual_url = self.config.get('backend', {}).get('manual_url')
            return manual_url
            
    def validate_models(self, base_url: str) -> Tuple[bool, List[str]]:
        """Validate that required models are available"""
        try:
            models_endpoint = f"{base_url}/models"
            response = requests.get(models_endpoint, timeout=30)
            
            if response.status_code != 200:
                return False, [f"Failed to fetch models from {models_endpoint}"]
                
            available_models = [model['id'] for model in response.json().get('data', [])]
            
            # Check primary models
            required_models = [
                self.config['models']['local1'],
                self.config['models']['local2'], 
                self.config['models']['local3']
            ]
            
            missing_models = [model for model in required_models if model not in available_models]
            
            if missing_models:
                return False, [f"Missing models: {missing_models}"]
                
            return True, []
            
        except Exception as e:
            return False, [f"Error validating models: {str(e)}"]
            
    def create_config_lists(self, base_url: str) -> Dict[str, List[Dict]]:
        """Create configuration lists for autogen"""
        models = self.config['models']
        
        config_lists = {
            'local1': [{
                "model": models['local1'],
                "base_url": base_url,
                "api_key": os.getenv("DEEPSEEK_API_KEY", "dummy-key")
            }],
            'local2': [{
                "model": models['local2'],
                "base_url": base_url,
                "api_key": os.getenv("DEEPSEEK_API_KEY", "dummy-key")
            }],
            'local3': [{
                "model": models['local3'],
                "base_url": base_url,
                "api_key": os.getenv("DEEPSEEK_API_KEY", "dummy-key")
            }]
        }
        
        return config_lists
        
    def create_agents(self, config_lists: Dict[str, List[Dict]], prompt_data: Dict = None) -> List[autogen.Agent]:
        """Create autogen agents from configuration"""
        agents = []
        
        # Customize system messages based on prompt type if provided
        prompt_type = prompt_data.get('prompt_type', 'text') if prompt_data else 'text'
        
        for agent_config in self.config['agents']:
            if agent_config['type'] == 'UserProxyAgent':
                system_message = agent_config['system_message']
                if prompt_data:
                    system_message += f" Focus on {prompt_type} content generation."
                # Add explicit tool availability notice
                system_message += " You have access to web_research_tool() for current information and research."
                
                agent = autogen.UserProxyAgent(
                    name=agent_config['name'],
                    system_message=system_message,
                    code_execution_config=agent_config.get('code_execution_config', {
                        "last_n_messages": 2,
                        "work_dir": self.config['processing']['output_directory'],
                        "use_docker": False,
                    }),
                    human_input_mode=agent_config.get('human_input_mode', 'TERMINATE'),
                )
            else:
                config_assignment = agent_config.get('config_assignment', 'local1')
                llm_config = None
                
                if config_assignment in config_lists:
                    llm_config = {"config_list": config_lists[config_assignment]}
                
                system_message = agent_config['system_message']
                if prompt_data:
                    metadata = prompt_data.get('metadata', {})
                    style = metadata.get('style')
                    tone = metadata.get('tone')
                    if style or tone:
                        system_message += f" Create {prompt_type} content"
                        if style:
                            system_message += f" in {style} style"
                        if tone:
                            system_message += f" with a {tone} tone"
                        system_message += "."
                # Add explicit tool availability notice for AssistantAgents
                system_message += " You have access to web_research_tool() for researching current information."
                
                agent = autogen.AssistantAgent(
                    name=agent_config['name'],
                    system_message=system_message,
                    llm_config=llm_config,
                )
            
            agents.append(agent)
            
            # Register database functions for agents with file save capability
            if agent_config.get('has_file_save_function', False):
                self.register_agent_functions(agent, agent_config['name'], prompt_data)
                
        return agents
        
    def register_agent_functions(self, agent, agent_name: str, prompt_data: Dict = None):
        """Register file save and database functions for an agent"""
        
        # File save function
        def save_file_function(content: str, folder: Optional[str] = None) -> Tuple[str, str]:
            return save_text_to_file(content, self.config['processing']['output_directory'])
        
        # Database save function
        def save_to_database(
            content: str, 
            title: Optional[str] = None,
            content_type: Optional[str] = None,
            tags: Optional[List[str]] = None,
            publication_status: str = "ready",
            notes: Optional[str] = None
        ) -> Tuple[str, int]:
            # Use prompt type as default content type
            if not content_type and prompt_data:
                content_type = prompt_data.get('prompt_type', 'text')
                if content_type not in ['poetry', 'prose', 'dialogue', 'erotica', 'satire', 'political', 'fragment']:
                    content_type = 'prose'  # Default fallback
            
            prompt_note = ""
            if prompt_data:
                prompt_note = f"Generated from prompt #{prompt_data.get('id', 'unknown')}. "
                metadata = prompt_data.get('metadata', {})
                if metadata:
                    prompt_note += f"Style: {metadata.get('style', 'auto')}, Tone: {metadata.get('tone', 'natural')}. "
            
            return save_to_sqlite_database(
                content=content,
                db_path=self.config['database']['path'],
                title=title,
                content_type=content_type,
                tags=tags,
                publication_status=publication_status,
                notes=f"{prompt_note}Generated by {agent_name} (automated). {notes or ''}"
            )
        
        # Database query function
        def query_database(
            search_query: Optional[str] = None,
            content_type: Optional[str] = None,
            limit: int = 5
        ) -> str:
            return query_database_content(
                db_path=self.config['database']['path'],
                search_query=search_query,
                content_type=content_type,
                limit=limit
            )
        
        # Database stats function
        def get_stats() -> str:
            return get_database_stats(self.config['database']['path'])
        
        # Web research tool for current information
        def web_research_tool(
            query: str,
            search_type: str = "web_search",
            search_depth: str = "advanced",
            max_results: int = 3
        ) -> Tuple[str, str]:
            """
            Research current information and events using web search.
            
            Args:
                query: What to research (e.g., "latest AI developments", "current weather in Paris")
                search_type: "web_search", "qna_search", or "context_search"
                search_depth: "basic" or "advanced" (advanced recommended for creative work)
                max_results: Number of sources to check (1-10, default: 3 for focused results)
                
            Returns:
                Tuple[str, str]: (status_message, research_content)
                
            Examples:
                - web_research_tool("latest technology trends", "web_search")
                - web_research_tool("What happened in Gaza this week?", "qna_search")
                - web_research_tool("climate change recent developments", "context_search")
            """
            # Log research activity
            self.logger.info(f"🔍 {agent_name} researching: '{query}' (type: {search_type}, depth: {search_depth})")
            
            try:
                status, content = tavily_research_assistant(
                    query=query,
                    search_type=search_type,
                    search_depth=search_depth,
                    max_results=max_results
                )
                
                if status.startswith("✅"):
                    self.logger.info(f"✅ {agent_name} research successful: {len(content)} chars received")
                    # Log a preview of the research content
                    preview = content[:150].replace('\n', ' ') + "..." if len(content) > 150 else content
                    self.logger.info(f"📝 Research preview: {preview}")
                else:
                    self.logger.warning(f"⚠️ {agent_name} research failed: {status}")
                
                return status, content
                
            except Exception as e:
                error_msg = f"❌ Research error for {agent_name}: {str(e)}"
                self.logger.error(error_msg)
                return error_msg, ""
        
        # Register functions based on agent type
        if isinstance(agent, autogen.UserProxyAgent):
            # UserProxyAgent: Only execution functions
            self.logger.info(f"⚙️ Registering execution functions for {agent_name} (UserProxyAgent)")
            agent.register_for_execution()(save_file_function)
            agent.register_for_execution()(save_to_database)
            agent.register_for_execution()(query_database)
            agent.register_for_execution()(get_stats)
            agent.register_for_execution()(web_research_tool)
            self.logger.info(f"✅ Execution registration complete for {agent_name}")
            
        elif isinstance(agent, autogen.AssistantAgent):
            # AssistantAgent: Only LLM functions
            self.logger.info(f"🤖 Registering LLM functions for {agent_name} (AssistantAgent)")
            agent.register_for_llm(description="Save text content to timestamped file")(save_file_function)
            agent.register_for_llm(description="Save content to Anthony's Musings database with intelligent analysis")(save_to_database)
            agent.register_for_llm(description="Query Anthony's Musings database for existing content")(query_database)
            agent.register_for_llm(description="Get statistics about Anthony's Musings database content")(get_stats)
            
            # Web research tool for AI agents
            agent.register_for_llm(description="""Research current information and events using web search.
            Use this tool to get up-to-date information about any topic for creative writing.
            Perfect for current events, recent developments, trending topics, or fact-checking.
            Returns clean, focused information ready to incorporate into creative writing.
            
            IMPORTANT: search_type must be one of: "web_search", "qna_search", or "context_search"
            - Use "web_search" for general research and current events
            - Use "qna_search" for specific questions 
            - Use "context_search" for detailed background information
            
            Examples:
            - web_research_tool("latest AI developments", "web_search") - for tech-themed writing
            - web_research_tool("current political events", "web_search") - for satirical pieces  
            - web_research_tool("recent cultural trends", "qna_search") - for contemporary references
            - web_research_tool("breaking news today", "web_search") - for current event inspiration
            - web_research_tool("weather in Paris", "context_search") - for location-specific details
            
            Always use this when you need current, real-world information for your writing.""")(web_research_tool)
            self.logger.info(f"✅ LLM registration complete for {agent_name} (including web_research_tool)")
            
        else:
            self.logger.warning(f"⚠️ Unknown agent type for {agent_name}: {type(agent).__name__}")

    def _create_structured_prompt_agents(self, config_lists: Dict, prompt_data: Dict) -> List:
        """
        Create specialized agents for generating structured JSON prompts.
        These agents are instructed to output valid JSON for image/lyrics prompts.
        """
        agents = []
        prompt_type = prompt_data.get('prompt_type', 'text')

        # Determine JSON schema based on prompt type
        if prompt_type == 'image_prompt':
            json_instruction = """
            You must output ONLY valid JSON following this exact schema:
            {
                "prompt": "detailed image description with style, composition, lighting",
                "negative_prompt": "things to avoid in the image",
                "style_tags": ["tag1", "tag2", "tag3"],
                "technical_params": {
                    "aspect_ratio": "16:9",
                    "quality": "high",
                    "mood": "describe the mood"
                },
                "composition": {
                    "subject": "main subject description",
                    "background": "background setting",
                    "lighting": "lighting description"
                }
            }

            Create a vivid, detailed image prompt based on the user's request.
            Output ONLY the JSON object, no other text.
            """
        elif prompt_type == 'lyrics_prompt':
            json_instruction = """
            You must output ONLY valid JSON following this exact schema:
            {
                "title": "Song Title",
                "genre": "genre name",
                "mood": "emotional mood",
                "tempo": "slow/medium/fast",
                "structure": [
                    {"type": "verse", "number": 1, "lyrics": "verse lyrics here..."},
                    {"type": "chorus", "lyrics": "chorus lyrics here..."}
                ],
                "metadata": {
                    "key": "musical key",
                    "time_signature": "4/4",
                    "vocal_style": "vocal description",
                    "instrumentation": ["instrument1", "instrument2"]
                }
            }

            Create complete song lyrics with structure based on the user's request.
            Output ONLY the JSON object, no other text.
            """
        else:
            json_instruction = "Output valid JSON based on the user's request."

        # Create modified agent configurations with JSON instruction
        for agent_config in self.config.get('agents', []):
            agent_name = agent_config['name']
            agent_type = agent_config['type']

            # Skip ContentManager for structured prompts - we only need the creative agents
            if agent_type == 'UserProxyAgent':
                continue

            # Add JSON instruction to system message
            original_system_message = agent_config.get('system_message', '')
            enhanced_system_message = f"{original_system_message}\n\n{json_instruction}"

            # Get config assignment
            config_assignment = agent_config.get('config_assignment', 'none')
            llm_config = None

            if config_assignment != 'none' and config_assignment in config_lists:
                llm_config = {"config_list": config_lists[config_assignment]}

            # Create agent
            if agent_type == 'AssistantAgent':
                agent = autogen.AssistantAgent(
                    name=agent_name,
                    system_message=enhanced_system_message,
                    llm_config=llm_config
                )
                agents.append(agent)
                self.logger.info(f"Created structured prompt agent: {agent_name}")

        return agents

    def _run_structured_prompt_generation(self, base_url: str, prompt_data: Dict) -> bool:
        """
        Generate structured JSON prompts for image/lyrics that will be processed
        by the offline ComfyUI app. Saves JSON as text to the database.
        """
        try:
            prompt_id = prompt_data['id']
            prompt_text = prompt_data['prompt_text']
            prompt_type = prompt_data.get('prompt_type', 'text')

            self.logger.info(f"Starting structured prompt generation for #{prompt_id} ({prompt_type})")

            # Update status to processing
            self.update_prompt_status(prompt_id, 'processing')

            # Create configuration lists
            config_lists = self.create_config_lists(base_url)

            # Create specialized agents for structured output
            agents = self._create_structured_prompt_agents(config_lists, prompt_data)

            if len(agents) < 1:
                self.logger.error("Need at least 1 agent for structured prompt generation")
                self.update_prompt_status(prompt_id, 'failed', 'No agents available')
                return False

            # Build the prompt
            enhanced_prompt = f"Create a structured {prompt_type} based on: {prompt_text}"

            # For structured prompts, use a simpler setup - direct agent chat
            # Since we only need JSON output, we don't need complex group chat
            primary_agent = agents[0]

            # Create a simple user proxy to receive the response
            user_proxy = autogen.UserProxyAgent(
                name="StructuredPromptCollector",
                human_input_mode="NEVER",
                max_consecutive_auto_reply=0,
                code_execution_config=False
            )

            # Initiate chat
            user_proxy.initiate_chat(
                primary_agent,
                message=enhanced_prompt,
                max_turns=1
            )

            # Extract the JSON response from chat history
            # AutoGen stores messages as: user_proxy.chat_messages[agent] = list of messages
            # We want the last message from the agent (the assistant's response)
            chat_history = user_proxy.chat_messages.get(primary_agent, [])
            json_response = None

            # Look for the agent's response (last non-user message with content)
            for message in reversed(chat_history):
                # In AutoGen, agent responses have 'name' field matching the agent name
                if message.get('name') == primary_agent.name and message.get('content'):
                    json_response = message['content'].strip()
                    self.logger.info(f"Extracted JSON response ({len(json_response)} chars)")
                    break

            if not json_response or not json_response.startswith('{'):
                self.logger.error(f"No valid JSON response received from agent for prompt #{prompt_id}")
                self.update_prompt_status(prompt_id, 'failed', 'No valid JSON response from agent')
                return False

            # Save the JSON to the database
            from tools import save_to_sqlite_database

            db_path = self.config.get('database', {}).get('path')
            status_msg, writing_id = save_to_sqlite_database(
                content=json_response,
                db_path=db_path,
                title=f"{prompt_type.replace('_', ' ').title()}: {prompt_text[:50]}...",
                content_type=prompt_type,
                publication_status='draft',
                notes=f"Structured JSON prompt for offline media generation (Prompt #{prompt_id})"
            )

            self.logger.info(status_msg)

            # Link the writing to the prompt
            if writing_id > 0:
                conn = sqlite3.connect(db_path, timeout=30.0)
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE prompts SET output_reference = ? WHERE id = ?",
                        (writing_id, prompt_id)
                    )
                    cursor.execute(
                        "UPDATE writings SET source_prompt_id = ? WHERE id = ?",
                        (prompt_id, writing_id)
                    )
                    conn.commit()
                finally:
                    conn.close()

                self.logger.info(f"Linked writing #{writing_id} to prompt #{prompt_id}")

            # Mark as completed with artifact_status='pending' so offline app knows to process it
            self.update_prompt_status(prompt_id, 'completed', artifact_status='pending')
            self.logger.info(f"Structured prompt generation completed for #{prompt_id}, marked as pending for media generation")
            return True

        except Exception as e:
            self.logger.error(f"Error in structured prompt generation: {str(e)}")
            self.update_prompt_status(prompt_id, 'failed', str(e))
            return False

    def run_generation_session(self, base_url: str, prompt_data: Dict) -> bool:
        """Run a content generation session for a specific prompt"""
        try:
            prompt_id = prompt_data['id']
            prompt_text = prompt_data['prompt_text']
            prompt_type = prompt_data.get('prompt_type', 'text')

            # Route structured prompt types to specialized handler
            if prompt_type in ['image_prompt', 'lyrics_prompt']:
                self.logger.info(f"Routing {prompt_type} #{prompt_id} to structured prompt generation")
                return self._run_structured_prompt_generation(base_url, prompt_data)

            self.logger.info(f"Starting generation for prompt #{prompt_id}: {prompt_text[:100]}...")

            # Update status to processing
            self.update_prompt_status(prompt_id, 'processing')
            
            # Create configuration lists
            config_lists = self.create_config_lists(base_url)
            
            # Create agents with prompt context
            agents = self.create_agents(config_lists, prompt_data)
            
            if len(agents) < 2:
                self.logger.error("Need at least 2 agents to run group chat")
                return False
            
            # Build enhanced prompt with metadata
            enhanced_prompt = prompt_text
            metadata = prompt_data.get('metadata', {})
            
            # Add style/tone/length hints for the AI agents
            metadata_hints = []
            if metadata.get('style'): metadata_hints.append(f"Style: {metadata['style']}")
            if metadata.get('tone'): metadata_hints.append(f"Tone: {metadata['tone']}")  
            if metadata.get('length'): metadata_hints.append(f"Length: {metadata['length']}")
            if metadata.get('collaboration_mode') and metadata['collaboration_mode'] != 'standard':
                metadata_hints.append(f"Mode: {metadata['collaboration_mode']}")
            
            if metadata_hints:
                enhanced_prompt += f" ({', '.join(metadata_hints)})"
            
            # Setup group chat
            groupchat = autogen.GroupChat(
                agents=agents,
                messages=[f"Create {prompt_type} content based on this prompt: {enhanced_prompt}"],
                max_round=self.config['processing'].get('max_rounds', 20)
            )
            
            # Get manager config
            manager_config_assignment = self.config.get('group_chat_manager', {}).get('config_assignment', 'local3')
            manager_llm_config = None
            
            if manager_config_assignment in config_lists:
                manager_llm_config = {"config_list": config_lists[manager_config_assignment]}
            
            manager = autogen.GroupChatManager(
                groupchat=groupchat,
                llm_config=manager_llm_config
            )
            
            # Start the chat
            agents[0].initiate_chat(manager, message=enhanced_prompt)
            
            # Mark as completed
            self.update_prompt_status(prompt_id, 'completed')
            self.logger.info(f"Generation completed successfully for prompt #{prompt_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error in generation session: {str(e)}")
            self.update_prompt_status(prompt_id, 'failed', str(e))
            return False
    
    def process_media_prompt(self, prompt: Dict[str, Any]) -> bool:
        """Process a media prompt via the configured pipeline."""
        prompt_id = prompt['id']
        prompt_type = (prompt.get('prompt_type') or '').lower()
        pipeline_key = self.media_prompt_type_map.get(prompt_type)

        if not pipeline_key:
            self.logger.warning(
                f"No media pipeline configured for prompt type '{prompt_type}'"
            )
            self.update_prompt_status(
                prompt_id,
                'failed',
                error_message=f"No media pipeline for prompt type '{prompt_type}'",
                artifact_status='unsupported',
            )
            return False

        pipeline = self.media_pipelines.get(pipeline_key)
        if not pipeline:
            self.logger.warning(
                f"Media pipeline '{pipeline_key}' is not available for prompt #{prompt_id}"
            )
            self.update_prompt_status(
                prompt_id,
                'failed',
                error_message=f"Media pipeline '{pipeline_key}' is unavailable",
                artifact_status='unsupported',
            )
            return False

        if not self.media_available:
            if self._check_comfyui_health():
                self.media_available = True
            else:
                self.logger.warning(
                    f"ComfyUI is unavailable; skipping media prompt #{prompt_id}"
                )
                self.update_prompt_status(
                    prompt_id,
                    'failed',
                    error_message="ComfyUI host is unavailable",
                    artifact_status='error',
                )
                return False

        self.update_prompt_status(
            prompt_id,
            'processing',
            artifact_status='processing',
        )

        try:
            result = pipeline.run(
                prompt_id=prompt_id,
                prompt_text=prompt.get('prompt_text', ''),
                metadata=prompt.get('metadata'),
            )
            artifacts: List[MediaArtifact] = result.get('artifacts', [])
            self.record_prompt_artifacts(prompt_id, artifacts)

            summary_metadata = {
                "duration_seconds": result.get('duration_seconds'),
                "run_directory": result.get('run_directory'),
                "stdout_tail": (result.get('stdout') or "")[-2000:],
                "stderr_tail": (result.get('stderr') or "")[-2000:],
                "artifact_count": len(artifacts),
            }

            self.update_prompt_status(
                prompt_id,
                'completed',
                artifact_status='ready',
                artifact_metadata=summary_metadata,
            )
            self.logger.info(
                f"Media generation succeeded for prompt #{prompt_id} "
                f"({len(artifacts)} artifact(s))"
            )
            return True

        except MediaPipelineError as exc:
            self.logger.error(
                f"Media pipeline error for prompt #{prompt_id}: {exc}"
            )
            self.update_prompt_status(
                prompt_id,
                'failed',
                error_message=str(exc),
                artifact_status='error',
            )
        except Exception as exc:
            self.logger.error(
                f"Unexpected media processing failure for prompt #{prompt_id}: {exc}"
            )
            self.update_prompt_status(
                prompt_id,
                'failed',
                error_message=str(exc),
                artifact_status='error',
            )

        return False
    
    def test_configuration(self) -> bool:
        """Test the service configuration"""
        self.logger.info("Testing service configuration...")
        
        # Check environment
        if not self.check_environment():
            return False
        
        # Test primary backend
        backend_config = self.config.get('backend', {})
        primary_backend = backend_config.get('type', 'oll')
        base_url = self.get_base_url(primary_backend)
        
        if not base_url:
            self.logger.error(f"No base URL available for backend type: {primary_backend}")
            return False
        
        self.logger.info(f"Testing primary backend: {primary_backend} ({base_url})")
        
        # Validate models
        if self.config['processing'].get('validate_models_on_startup', True):
            valid, errors = self.validate_models(base_url)
            if not valid:
                self.logger.error(f"Model validation failed: {errors}")
                return False
        
        # Test database access
        db_path = self.config['database']['path']
        if not os.path.exists(db_path):
            self.logger.error(f"Database not found at: {db_path}")
            return False
        
        if self.media_enabled:
            if not self.media_pipelines:
                self.logger.warning(
                    "Media support is enabled but no pipelines are available. "
                    "Media prompts will be skipped."
                )
            elif self._check_comfyui_health():
                self.media_available = True
            else:
                self.media_available = False
                self.logger.warning(
                    "ComfyUI host is unreachable during configuration test; "
                    "media prompts will be skipped until connectivity is restored."
                )

        self.logger.info("Configuration test passed!")
        return True
    
    def run_queue_processor(self):
        """Process unprocessed prompts from the queue - FIXED VERSION"""
        self.logger.info("Starting queue processor...")
        
        # Use process lock to prevent concurrent execution
        try:
            with ProcessLock(self.lock_file, timeout_minutes=45):
                self.logger.info("Acquired process lock - checking for unprocessed prompts")
                
                # 🔥 FIX: Check for prompts FIRST - before any expensive operations
                prompts = self.get_unprocessed_prompts()
                
                if not prompts:
                    self.logger.info("No unprocessed prompts found - exiting without model validation")
                    return  # ✅ Early exit - no GPU usage!
                
                self.logger.info(f"Found {len(prompts)} unprocessed prompts - proceeding with validation")
                
                # Only check environment and models if we have work to do
                if not self.check_environment():
                    self.logger.error("Environment check failed")
                    return
                
                # Determine backend URL
                backend_config = self.config.get('backend', {})
                primary_backend = backend_config.get('type', 'oll')
                base_url = self.get_base_url(primary_backend)
                
                if not base_url:
                    self.logger.error(f"No base URL available for backend type: {primary_backend}")
                    return
                
                # 🔥 FIX: Only validate models if we have prompts to process
                if self.config['processing'].get('validate_models_on_startup', True):
                    self.logger.info("Validating models for active prompt processing...")
                    valid, errors = self.validate_models(base_url)
                    if not valid:
                        self.logger.error(f"Model validation failed: {errors}")
                        return
                
                # Process each prompt
                for prompt in prompts:
                    self.logger.info(f"Processing prompt #{prompt['id']}: {prompt['prompt_text'][:50]}...")
                    prompt_type = (prompt.get('prompt_type') or 'text').lower()

                    if self.media_enabled and prompt_type in self.media_prompt_type_map:
                        success = self.process_media_prompt(prompt)
                    else:
                        success = self.run_generation_session(base_url, prompt)
                    
                    if success:
                        self.logger.info(f"Successfully processed prompt #{prompt['id']}")
                    else:
                        self.logger.error(f"Failed to process prompt #{prompt['id']}")
                    
                    # Small delay between prompts to avoid overwhelming the system
                    time.sleep(2)
                
                self.logger.info("Queue processing completed")
                
        except RuntimeError as e:
            self.logger.info(f"Skipping execution: {e}")
        except Exception as e:
            self.logger.error(f"Error in queue processor: {e}")

    def run_service(self):
        """Main service execution - for manual/direct prompts"""
        self.logger.info(f"Starting {self.config['service_info']['name']} v{self.config['service_info']['version']}")
        
        # Check environment
        if not self.check_environment():
            sys.exit(1)
        
        # Determine backend URL
        backend_config = self.config.get('backend', {})
        primary_backend = backend_config.get('type', 'oll')
        base_url = self.get_base_url(primary_backend)
        
        if not base_url:
            self.logger.error(f"No base URL available for backend type: {primary_backend}")
            sys.exit(1)
        
        # Validate models if required
        if self.config['processing'].get('validate_models_on_startup', True):
            valid, errors = self.validate_models(base_url)
            if not valid:
                self.logger.error(f"Model validation failed: {errors}")
                sys.exit(1)
        
        # Generate a random prompt for testing
        import random
        test_prompts = [
            "Write a short poem about the intersection of technology and human emotion",
            "Create a dialogue between two characters discussing the nature of creativity",
            "Write a brief prose piece about a moment of unexpected beauty"
        ]
        
        test_prompt_data = {
            'id': 999,
            'prompt_text': random.choice(test_prompts),
            'prompt_type': 'text',
            'metadata': {}
        }
        
        # Run generation session
        success = self.run_generation_session(base_url, test_prompt_data)
        
        if success:
            self.logger.info("Service execution completed successfully")
        else:
            self.logger.error("Service execution failed")
            sys.exit(1)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Poets Generator Service v3.1')
    parser.add_argument('config_file', nargs='?', default='poets_cron_config.json',
                       help='Configuration file path')
    parser.add_argument('--test', action='store_true',
                       help='Test configuration and exit')
    parser.add_argument('--queue', action='store_true',
                       help='Process the prompt queue (for LaunchAgent)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.config_file):
        print(f"ERROR: Configuration file not found: {args.config_file}")
        sys.exit(1)
    
    # Create service instance
    service = PoetsService(args.config_file)
    
    if args.test:
        # Run configuration test
        success = service.test_configuration()
        sys.exit(0 if success else 1)
    elif args.queue:
        # Process the queue (for LaunchAgent)
        service.run_queue_processor()
    else:
        # Run the service with a test prompt
        service.run_service()


if __name__ == "__main__":
    main()
