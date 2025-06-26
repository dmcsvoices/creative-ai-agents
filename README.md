# Poets Service Clean

An automated content generation service that uses AI agents to create poetry, prose, dialogue, and other creative writing. Built with AutoGen and designed to work with local LLM backends.

## Features

- **Multi-Agent System**: Uses AutoGen to coordinate multiple AI agents (Anthony, Cindy, ContentManager)
- **Queue Processing**: Processes prompts from a database queue for automated generation
- **Web Research Integration**: Uses Tavily API for current information and research
- **Database Integration**: Saves generated content to SQLite database with intelligent analysis
- **Flexible Backend Support**: Works with Ollama, LM Studio, or custom OpenAI-compatible APIs
- **Process Locking**: Prevents concurrent executions with file-based locking
- **Comprehensive Logging**: Detailed logging for monitoring and debugging

## Architecture

### Core Components

1. **poets_cron_service_v3.py** - Main service orchestrator
2. **tools.py** - Database operations and Tavily web research functions
3. **control.sh** - Service control script for start/stop/status
4. **poets_cron_config.json** - Configuration file

### Agent Roles

- **ContentManager** (UserProxyAgent): Coordinates the creative process and saves content
- **Anthony** (AssistantAgent): Creative writer specializing in poetry and prose
- **Cindy** (AssistantAgent): Dialogue specialist and conversation creator

## Prerequisites

- Python 3.8+
- SQLite database for storing prompts and generated content
- Local LLM backend (Ollama, LM Studio, etc.)
- Tavily API key for web research functionality

## Setup

### 1. Environment Variables

Set the following environment variables:

```bash
export TVLY_API_KEY="your_tavily_api_key_here"
export NGROKURL="http://localhost:1234/v1"  # For LM Studio
export WIFI_LLM_URL="http://localhost:11434/v1"  # For Ollama
export DEEPSEEK_API_KEY="dummy-key"  # Can be dummy for local models
```

### 2. Install Dependencies

```bash
# Create virtual environment
python3 -m venv poets_env
source poets_env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure the Service

Edit `poets_cron_config.json`:

- Update database path to your SQLite database
- Configure your available models
- Set backend type (`lms` for LM Studio, `oll` for Ollama)
- Adjust agent system messages as needed

### 4. Database Setup

Ensure your SQLite database has the required tables:

```sql
-- Prompts table for queue processing
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
);

-- Writings table for generated content
CREATE TABLE IF NOT EXISTS writings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    content_type TEXT,
    content TEXT,
    original_filename TEXT,
    word_count INTEGER,
    character_count INTEGER,
    line_count INTEGER,
    mood TEXT,
    explicit_content BOOLEAN,
    publication_status TEXT,
    notes TEXT,
    file_timestamp TIMESTAMP,
    content_hash TEXT,
    content_fingerprint TEXT
);
```

## Usage

### Queue Processing Mode (Recommended)

Process prompts from the database queue:

```bash
python3 poets_cron_service_v3.py --queue
```

### Test Configuration

Verify your setup:

```bash
python3 poets_cron_service_v3.py --test
```

### Direct Execution

Run with a random test prompt:

```bash
python3 poets_cron_service_v3.py
```

### Service Control

Use the control script for service management:

```bash
./control.sh start    # Start the service
./control.sh stop     # Stop the service
./control.sh status   # Check status
./control.sh restart  # Restart the service
```

## Configuration

### Backend Types

- **lms**: LM Studio (uses NGROKURL)
- **oll**: Ollama (uses WIFI_LLM_URL)
- **manual**: Custom URL (set in config)

### Model Configuration

The service supports three model slots with fallback options:

```json
{
  "models": {
    "local1": "your-model-1",
    "local2": "your-model-2", 
    "local3": "your-model-3"
  },
  "model_fallbacks": {
    "enabled": true,
    "fallback_backend": "lms",
    "fallback_models": {
      "local1": "fallback-model-1",
      "local2": "fallback-model-2",
      "local3": "fallback-model-3"
    }
  }
}
```

### Agent Customization

Modify agent system messages in the config to change their behavior:

```json
{
  "agents": [
    {
      "name": "Anthony",
      "system_message": "Your custom system message here...",
      "config_assignment": "local1"
    }
  ]
}
```

## Web Research Features

The service includes powerful web research capabilities via Tavily:

- **tavily_web_search()**: General web search with AI-generated answers
- **tavily_qna_search()**: Direct question answering
- **tavily_get_search_context()**: Background research for RAG applications
- **tavily_research_assistant()**: Unified research tool for creative writing

Agents can use the `web_research_tool()` function to gather current information for their creative work.

## Database Functions

- **save_to_sqlite_database()**: Intelligent content analysis and storage
- **query_database_content()**: Search existing content
- **get_database_stats()**: Database statistics

## Process Management

The service uses file-based locking to prevent concurrent executions:

- Lock file: `poets_generation.lock`
- Automatic stale lock cleanup
- Configurable timeout (default: 45 minutes)

## Logging

Comprehensive logging to `logs/poets_cron.log`:

- Service startup/shutdown
- Prompt processing status
- Model validation results
- Web research activity
- Error tracking

## Security Considerations

- API keys are read from environment variables only
- Database paths should be absolute and secure
- Log files may contain generated content
- Process locks prevent resource conflicts

## Troubleshooting

### Common Issues

1. **Model validation failed**: Check that your LLM backend is running and models are available
2. **Environment variables not set**: Verify all required environment variables are exported
3. **Database not found**: Check the database path in your config file
4. **Process lock errors**: Ensure no other instances are running or manually remove lock file

### Debug Mode

Enable debug logging by setting the log level to "DEBUG" in the config file.

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]