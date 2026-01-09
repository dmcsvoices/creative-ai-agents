import datetime
import sqlite3
import os
import re
from typing import Tuple, Optional, List, Dict, Any
import time
import random

def save_text_to_file(content: str, folder: Optional[str] = None) -> Tuple[str, str]:
    """Saves text to a timestamped file.
    
    Args:
        content: Text data (any Unicode characters).
        folder: Path to save the file. Defaults to current directory.
        
    Returns:
        Tuple[str, str]: (filename, full_path)
    """
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S.%f")[:-3]
    filename = f"{timestamp}.txt"
    
    if folder:
        full_path = f"{folder.rstrip('/')}/{filename}"
    else:
        full_path = filename
    
    with open(full_path, "w", encoding="utf-8") as file:
        file.write(content)
    
    return filename, full_path

def get_database_connection(db_path: str, timeout: int = 30):
    """Get database connection with proper configuration for concurrent access"""
    try:
        conn = sqlite3.connect(db_path, timeout=timeout)

        # Configure for concurrent access
        # Enable WAL mode to match main service connection
        # Safe now because main service initializes WAL mode first, and PRAGMA is idempotent
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=memory")
        conn.execute("PRAGMA busy_timeout=30000")  # 30 second timeout

        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise

def retry_database_operation(func, max_retries=3, base_delay=0.1):
    """Retry database operations with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                # Database is locked, wait and retry
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                print(f"Database locked, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                continue
            else:
                raise
        except Exception as e:
            raise

def save_to_sqlite_database(
    content: str, 
    db_path: Optional[str] = None,
    title: Optional[str] = None,
    content_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    publication_status: str = "draft",
    notes: Optional[str] = None
) -> Tuple[str, int]:
    """
    Save content to Anthony's Musings SQLite database with intelligent preprocessing.
    Fixed for concurrent access and flexible content types.
    
    Args:
        content: The text content to save
        db_path: Path to SQLite database (defaults to anthonys_musings.db)
        title: Optional title (will be auto-generated if not provided)
        content_type: Optional content type (will be auto-detected if not provided)
        tags: Optional list of tags to apply
        publication_status: Publication status (default: "draft")
        notes: Optional notes about the content
        
    Returns:
        Tuple[str, int]: (status_message, writing_id)
    """
    
    # Default database path
    if not db_path:
        db_path = "/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db"
    
    # Check if database exists
    if not os.path.exists(db_path):
        return f"Error: Database not found at {db_path}", -1
    
    def _save_operation():
        conn = get_database_connection(db_path)
        try:
            cursor = conn.cursor()
            
            # Auto-detect content properties
            detected_props = _analyze_content(content)
            
            # Use provided values or fall back to detected ones
            final_title = title or detected_props['title']
            final_content_type = content_type or detected_props['content_type']
            final_tags = tags or detected_props['tags']
            
            # Create filename for tracking
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S.%f")[:-3]
            filename = f"ai_generated_{timestamp}.txt"
            
            # Calculate metrics
            word_count = len(content.split())
            char_count = len(content)
            line_count = len([l for l in content.split('\n') if l.strip()])
            
            # Determine publication status based on content
            if detected_props['explicit']:
                final_status = 'explicit'
            elif publication_status == 'draft' and detected_props['quality_score'] > 7:
                final_status = 'ready'  # High quality content ready for publication
            else:
                final_status = publication_status
            
            # Combine notes
            auto_notes = f"AI Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            if detected_props['ai_confidence'] < 0.8:
                auto_notes += f" (Low confidence: {detected_props['ai_confidence']:.2f})"
            if notes:
                final_notes = f"{auto_notes}. {notes}"
            else:
                final_notes = auto_notes
            
            # Calculate content hash for duplicate detection
            import hashlib
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            # Create content fingerprint
            fingerprint = content[:100] + "..." + content[-100:] if len(content) > 200 else content
            
            # Insert into writings table - NO CHECK constraint issues now
            cursor.execute("""
                INSERT INTO writings (
                    title, content_type, content, original_filename,
                    word_count, character_count, line_count, mood, explicit_content,
                    publication_status, notes, file_timestamp, content_hash, content_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                final_title, final_content_type, content, filename,
                word_count, char_count, line_count, detected_props['mood'], 
                detected_props['explicit'], final_status, final_notes,
                datetime.datetime.now(), content_hash, fingerprint
            ))
            
            writing_id = cursor.lastrowid
            
            # Add to full-text search (if FTS table exists)
            try:
                cursor.execute("""
                    INSERT INTO writings_fts(rowid, title, content, notes) 
                    VALUES (?, ?, ?, ?)
                """, (writing_id, final_title, content, final_notes))
            except sqlite3.OperationalError:
                # FTS table might not exist, that's okay
                pass
            
            # Add tags
            tag_count = 0
            for tag_name in final_tags:
                tag_id = _get_or_create_tag(cursor, tag_name, detected_props['tag_types'].get(tag_name, 'subject'))
                cursor.execute("INSERT OR IGNORE INTO writing_tags (writing_id, tag_id) VALUES (?, ?)", 
                             (writing_id, tag_id))
                tag_count += 1
            
            conn.commit()
            
            # Create status message
            status_msg = f"✅ Saved to database: '{final_title}' (ID: {writing_id})\n"
            status_msg += f"   Type: {final_content_type}, Status: {final_status}\n"
            status_msg += f"   Words: {word_count}, Tags: {tag_count}\n"
            if detected_props['explicit']:
                status_msg += "   ⚠️ Marked as explicit content\n"
            
            return status_msg, writing_id
            
        finally:
            conn.close()
    
    try:
        return retry_database_operation(_save_operation)
    except Exception as e:
        return f"❌ Database error: {str(e)}", -1

def _analyze_content(content: str) -> Dict[str, Any]:
    """
    Intelligent content analysis for automatic categorization and tagging.
    Updated to be more flexible with content types.
    
    Returns:
        Dict with detected properties: title, content_type, tags, mood, etc.
    """
    lower = content.lower()
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    
    analysis = {
        'title': '',
        'content_type': 'fragment',  # Default fallback
        'tags': [],
        'tag_types': {},
        'mood': None,
        'explicit': False,
        'quality_score': 5,  # 1-10 scale
        'ai_confidence': 0.8  # Confidence in classification
    }
    
    # 1. TITLE EXTRACTION
    title_patterns = [
        r'\*\*Title:\s*["\']?([^"\'\n]+)["\']?',
        r'TITLE:\s*["\']?([^"\'\n]+)["\']?',
        r'Title:\s*["\']?([^"\'\n]+)["\']?',
        r'\*\*([^*\n]{1,80})\*\*',
        r'Chapter\s+\d+:\s*([^\n]{1,80})',
        r'O\s+([^,\n]{1,40}),',  # "O Name," pattern
    ]
    
    for pattern in title_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            analysis['title'] = match.group(1).strip()
            break
    
    # If no title found, use first meaningful line
    if not analysis['title'] and lines:
        first_line = lines[0]
        if len(first_line) < 100 and not first_line.startswith('---'):
            analysis['title'] = first_line
        else:
            analysis['title'] = f"AI Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    # 2. EXPLICIT CONTENT DETECTION
    explicit_indicators = ['cock', 'pussy', 'cum', 'fuck', 'squirt', 'dick', 'tits', 'butthole', 'orgasm']
    explicit_count = sum(lower.count(word) for word in explicit_indicators)
    analysis['explicit'] = explicit_count > 2
    
    # 3. CONTENT TYPE DETECTION - More flexible, any type allowed
    # Check for JSON-structured prompts first
    if '{' in content and '}' in content:
        # Image prompt detection
        if ('"prompt"' in content and '"style' in lower) or ('"composition"' in lower and '"lighting"' in lower):
            analysis['content_type'] = 'image_prompt'
            analysis['quality_score'] = 8
        # Lyrics prompt detection
        elif ('"structure"' in lower and 'verse' in lower) or ('"lyrics"' in lower and '"chorus"' in lower):
            analysis['content_type'] = 'lyrics_prompt'
            analysis['quality_score'] = 8
        # General JSON content
        elif '"' in content and ':' in content:
            # Don't override, continue to other checks
            pass

    if analysis['content_type'] == 'fragment':  # Only proceed if not already detected
        if analysis['explicit']:
            analysis['content_type'] = 'erotica'
            analysis['quality_score'] = 3  # Lower default for explicit
        elif ('anthony:' in lower and 'cindy:' in lower) or content.count('"') > 4:
            analysis['content_type'] = 'dialogue'
            analysis['quality_score'] = 7
        elif any(word in lower for word in ['trump', 'netanyahu', 'g20', 'summit', 'president']):
            analysis['content_type'] = 'political'
            analysis['quality_score'] = 8
        elif any(word in lower for word in ['hasbara', 'palestine', 'gaza', 'theme park', 'petting zoo']):
            analysis['content_type'] = 'satire'
            analysis['quality_score'] = 8
        elif 'chapter' in lower and len(content.split()) > 100:
            analysis['content_type'] = 'prose'
            analysis['quality_score'] = 7
        elif content.startswith('O ') and ',' in content[:50]:
            analysis['content_type'] = 'poetry'
            analysis['quality_score'] = 8
        elif '[verse]' in lower or '[chorus]' in lower or 'verse 1' in lower:
            analysis['content_type'] = 'song'
            analysis['quality_score'] = 7
        elif 'def ' in content or 'function ' in content or 'import ' in content:
            analysis['content_type'] = 'code'
            analysis['quality_score'] = 6
        else:
            # Check for poetry by structure
            if lines and len(lines) > 3:
                short_lines = sum(1 for l in lines if len(l) < 60)
                if short_lines / len(lines) > 0.6:
                    analysis['content_type'] = 'poetry'
                    analysis['quality_score'] = 6
                else:
                    analysis['content_type'] = 'fragment'
                    analysis['quality_score'] = 5
    
    # 4. MOOD DETECTION
    mood_indicators = {
        'erotic': ['arousal', 'desire', 'lust', 'passionate'] + explicit_indicators,
        'satirical': ['trump', 'ridiculous', 'absurd', 'theme park', 'netanyahu'],
        'playful': ['anthony:', 'cindy:', 'laugh', 'giggle', 'tease'],
        'passionate': ['fire', 'burn', 'wild', 'intense', 'fierce'],
        'contemplative': ['wonder', 'ponder', 'think', 'reflect', 'consider'],
        'melancholy': ['sad', 'lonely', 'tears', 'sorrow', 'empty', 'lost'],
        'angry': ['rage', 'fury', 'hate', 'anger', 'furious'],
        'romantic': ['love', 'heart', 'kiss', 'embrace', 'tender']
    }
    
    mood_scores = {}
    for mood, keywords in mood_indicators.items():
        score = sum(lower.count(keyword) for keyword in keywords)
        if score > 0:
            mood_scores[mood] = score
    
    if mood_scores:
        analysis['mood'] = max(mood_scores, key=mood_scores.get)
    
    # 5. TAG DETECTION AND CATEGORIZATION
    tag_detection = {
        # Character tags
        'cindy': ('character', ['cindy']),
        'anthony': ('character', ['anthony']),
        'eudora': ('character', ['eudora']),
        
        # Subject tags
        'trump': ('subject', ['trump', 'president trump', 'donald trump']),
        'palestine': ('subject', ['palestine', 'gaza', 'palestinian']),
        'hasbara': ('subject', ['hasbara', 'propaganda']),
        'technology': ('subject', ['gui', 'interface', 'code', 'programming', 'computer']),
        'chickens': ('subject', ['chicken', 'hen', 'rooster', 'cluck', 'coop']),
        'delivery_driver': ('subject', ['deliver', 'driver', 'car', 'engine', 'road']),
        
        # Style tags
        'dialogue': ('style', ['anthony:', 'cindy:', 'said', 'asked', 'replied']),
        'narrative': ('style', ['chapter', 'story', 'once upon', 'meanwhile']),
        'song_lyrics': ('style', ['verse', 'chorus', 'bridge', 'refrain']),
        
        # Theme tags
        'political_satire': ('theme', ['trump', 'netanyahu', 'political', 'satire']),
        'social_commentary': ('theme', ['society', 'social', 'commentary', 'critique']),
        
        # Content warnings
        'explicit_content': ('content_warning', explicit_indicators),
        'nsfw': ('content_warning', explicit_indicators if analysis['explicit'] else []),
        
        # Platform tags
        'twitter_ready': ('platform', []),  # Will be added based on length
        'instagram_ready': ('platform', []),
        'blog_ready': ('platform', [])
    }
    
    # Check each tag category
    for tag_name, (tag_type, keywords) in tag_detection.items():
        if any(keyword in lower for keyword in keywords):
            analysis['tags'].append(tag_name)
            analysis['tag_types'][tag_name] = tag_type
    
    # Special handling for explicit content
    if analysis['explicit']:
        analysis['tags'].extend(['explicit_content', 'nsfw'])
        analysis['tag_types']['explicit_content'] = 'content_warning'
        analysis['tag_types']['nsfw'] = 'content_warning'
    
    # Platform suitability based on length
    char_count = len(content)
    if char_count <= 280:
        analysis['tags'].append('twitter_ready')
        analysis['tag_types']['twitter_ready'] = 'platform'
    elif char_count <= 2200:
        analysis['tags'].append('instagram_ready') 
        analysis['tag_types']['instagram_ready'] = 'platform'
    
    if len(content.split()) > 100:
        analysis['tags'].append('blog_ready')
        analysis['tag_types']['blog_ready'] = 'platform'
    
    # Quality scoring adjustments
    if len(analysis['tags']) > 3:
        analysis['quality_score'] += 1  # Rich tagging indicates quality
    if word_count := len(content.split()):
        if 50 <= word_count <= 500:
            analysis['quality_score'] += 1  # Good length
        elif word_count > 1000:
            analysis['quality_score'] += 2  # Substantial content
    
    # Remove duplicates and limit tags
    analysis['tags'] = list(set(analysis['tags']))[:10]  # Max 10 tags
    
    return analysis

def _get_or_create_tag(cursor, tag_name: str, tag_type: str = 'subject') -> int:
    """Get existing tag ID or create new tag and return its ID"""
    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    row = cursor.fetchone()
    
    if row:
        return row[0]
    else:
        cursor.execute("INSERT INTO tags (name, tag_type) VALUES (?, ?)", (tag_name, tag_type))
        return cursor.lastrowid

def query_database_content(
    db_path: Optional[str] = None,
    search_query: Optional[str] = None,
    content_type: Optional[str] = None,
    limit: int = 10
) -> str:
    """
    Query the database for existing content (useful for AI agents to check for duplicates or references).
    Fixed for concurrent access.
    
    Args:
        db_path: Path to database
        search_query: Full-text search query
        content_type: Filter by content type
        limit: Maximum results to return
        
    Returns:
        Formatted string with query results
    """
    if not db_path:
        db_path = "/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db"
    
    if not os.path.exists(db_path):
        return f"Database not found at {db_path}"
    
    def _query_operation():
        conn = get_database_connection(db_path)
        try:
            cursor = conn.cursor()
            
            if search_query:
                # Try FTS search first, fall back to LIKE search
                try:
                    query = """
                    SELECT w.id, w.title, w.content_type, w.word_count, w.publication_status,
                           snippet(writings_fts, 1, '<b>', '</b>', '...', 32) as snippet
                    FROM writings_fts 
                    JOIN writings w ON writings_fts.rowid = w.id
                    WHERE writings_fts MATCH ?
                    """
                    params = [search_query]
                    
                    if content_type:
                        query += " AND w.content_type = ?"
                        params.append(content_type)
                    
                    query += f" ORDER BY rank LIMIT {limit}"
                    cursor.execute(query, params)
                except sqlite3.OperationalError:
                    # FTS not available, use LIKE search
                    query = """
                    SELECT id, title, content_type, word_count, publication_status,
                           substr(content, 1, 100) as preview
                    FROM writings WHERE (title LIKE ? OR content LIKE ?)
                    """
                    params = [f"%{search_query}%", f"%{search_query}%"]
                    
                    if content_type:
                        query += " AND content_type = ?"
                        params.append(content_type)
                    
                    query += f" ORDER BY file_timestamp DESC LIMIT {limit}"
                    cursor.execute(query, params)
            else:
                # Browse by type
                if content_type:
                    cursor.execute("""
                    SELECT id, title, content_type, word_count, publication_status,
                           substr(content, 1, 100) as preview
                    FROM writings WHERE content_type = ? 
                    ORDER BY file_timestamp DESC LIMIT ?
                    """, (content_type, limit))
                else:
                    cursor.execute("""
                    SELECT id, title, content_type, word_count, publication_status,
                           substr(content, 1, 100) as preview
                    FROM writings ORDER BY file_timestamp DESC LIMIT ?
                    """, (limit,))
            
            results = cursor.fetchall()
            
            if not results:
                return "No matching content found in database."
            
            # Format results
            output = f"Found {len(results)} results:\n\n"
            for i, row in enumerate(results, 1):
                output += f"{i}. {row[1]} (ID: {row[0]})\n"
                output += f"   Type: {row[2]}, Words: {row[3]}, Status: {row[4]}\n"
                if len(row) > 5 and row[5]:  # Preview/snippet
                    preview = row[5].replace('<b>', '**').replace('</b>', '**')
                    output += f"   Preview: {preview}\n"
                output += "\n"
            
            return output
        finally:
            conn.close()
    
    try:
        return retry_database_operation(_query_operation)
    except Exception as e:
        return f"Query error: {str(e)}"

def get_database_stats(db_path: Optional[str] = None) -> str:
    """Get database statistics for AI agents. Fixed for concurrent access."""
    if not db_path:
        db_path = "/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db"
    
    if not os.path.exists(db_path):
        return f"Database not found at {db_path}"
    
    def _stats_operation():
        conn = get_database_connection(db_path)
        try:
            cursor = conn.cursor()
            
            # Overall stats
            cursor.execute("SELECT COUNT(*), SUM(word_count), AVG(word_count) FROM writings")
            total, total_words, avg_words = cursor.fetchone()
            
            # By content type
            cursor.execute("""
            SELECT content_type, COUNT(*), 
                   SUM(CASE WHEN explicit_content = 1 THEN 1 ELSE 0 END) as explicit_count
            FROM writings GROUP BY content_type ORDER BY COUNT(*) DESC
            """)
            by_type = cursor.fetchall()
            
            # By status
            cursor.execute("SELECT publication_status, COUNT(*) FROM writings GROUP BY publication_status")
            by_status = cursor.fetchall()
            
            # Format output
            output = f"📊 Database Statistics:\n"
            output += f"Total pieces: {total}, Total words: {total_words:,}, Average: {avg_words:.1f}\n\n"
            
            output += "By Content Type:\n"
            for content_type, count, explicit in by_type:
                explicit_note = f" ({explicit} explicit)" if explicit > 0 else ""
                output += f"  {content_type}: {count}{explicit_note}\n"
            
            output += "\nBy Publication Status:\n"
            for status, count in by_status:
                output += f"  {status}: {count}\n"
            
            return output
        finally:
            conn.close()
    
    try:
        return retry_database_operation(_stats_operation)
    except Exception as e:
        return f"Stats error: {str(e)}"

# NEW TAVILY INTEGRATION FUNCTIONS

def tavily_web_search(
    query: str,
    search_depth: str = "basic",
    max_results: int = 5,
    include_answer: bool = True,
    include_raw_content: bool = False,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Perform web search using Tavily API for AI agents to get current information.
    
    Args:
        query: Search query string
        search_depth: "basic" or "advanced" search depth
        max_results: Maximum number of results (1-20, default: 5)
        include_answer: Whether to include AI-generated answer
        include_raw_content: Whether to include full raw content
        include_domains: List of domains to include (optional)
        exclude_domains: List of domains to exclude (optional)
        
    Returns:
        Tuple[str, Dict]: (formatted_results, raw_response)
    """
    try:
        # Import Tavily client
        try:
            import tavily
            TavilyClient = tavily.TavilyClient
        except ImportError:
            return "❌ Error: Tavily library not installed. Run: pip install tavily-python", {}
        
        # Get API key from environment
        api_key = os.getenv("TVLY_API_KEY")
        if not api_key:
            return "❌ Error: TVLY_API_KEY environment variable not set", {}
        
        # Initialize client
        client = TavilyClient(api_key=api_key)
        
        # Prepare search parameters
        search_params = {
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content
        }
        
        if include_domains:
            search_params["include_domains"] = include_domains
        if exclude_domains:
            search_params["exclude_domains"] = exclude_domains
        
        # Perform search
        response = client.search(**search_params)
        
        # Format results for AI agents
        formatted_output = f"🔍 Tavily Search Results for: '{query}'\n"
        formatted_output += f"📊 Found {len(response.get('results', []))} results\n\n"
        
        # Include AI answer if available
        if include_answer and response.get('answer'):
            formatted_output += f"🤖 AI Answer:\n{response['answer']}\n\n"
        
        # Format search results
        formatted_output += "📝 Search Results:\n"
        for i, result in enumerate(response.get('results', []), 1):
            formatted_output += f"{i}. {result.get('title', 'No title')}\n"
            formatted_output += f"   URL: {result.get('url', 'No URL')}\n"
            formatted_output += f"   Score: {result.get('score', 'N/A')}\n"
            
            if result.get('content'):
                content_preview = result['content'][:200]
                formatted_output += f"   Content: {content_preview}{'...' if len(result['content']) > 200 else ''}\n"
            
            formatted_output += "\n"
        
        return f"✅ Search completed successfully. Found {len(response.get('results', []))} results.", {
            "formatted_output": formatted_output,
            "raw_response": response
        }
        
    except Exception as e:
        return f"❌ Tavily search error: {str(e)}", {}

def tavily_extract_content(
    urls: List[str],
    include_images: bool = False
) -> Tuple[str, Dict[str, Any]]:
    """
    Extract content from URLs using Tavily API.
    
    Args:
        urls: List of URLs to extract content from (max 20)
        include_images: Whether to include images in extraction
        
    Returns:
        Tuple[str, Dict]: (formatted_results, raw_response)
    """
    try:
        # Import Tavily client
        try:
            import tavily
            TavilyClient = tavily.TavilyClient
        except ImportError:
            return "❌ Error: Tavily library not installed. Run: pip install tavily-python", {}
        
        # Get API key from environment
        api_key = os.getenv("TVLY_API_KEY")
        if not api_key:
            return "❌ Error: TVLY_API_KEY environment variable not set", {}
        
        # Validate input
        if not urls:
            return "❌ Error: No URLs provided", {}
        
        if len(urls) > 20:
            return "❌ Error: Maximum 20 URLs allowed", {}
        
        # Initialize client
        client = TavilyClient(api_key=api_key)
        
        # Extract content
        response = client.extract(urls=urls, include_images=include_images)
        
        # Format results
        formatted_output = f"📄 Tavily Content Extraction Results\n"
        formatted_output += f"📊 Processed {len(urls)} URLs\n"
        formatted_output += f"✅ Successfully extracted: {len(response.get('results', []))}\n"
        formatted_output += f"❌ Failed extractions: {len(response.get('failed_results', []))}\n\n"
        
        # Show successful extractions
        if response.get('results'):
            formatted_output += "📝 Extracted Content:\n"
            for i, result in enumerate(response['results'], 1):
                formatted_output += f"{i}. {result.get('url', 'Unknown URL')}\n"
                
                raw_content = result.get('raw_content', '')
                if raw_content:
                    content_preview = raw_content[:500]
                    formatted_output += f"   Content: {content_preview}{'...' if len(raw_content) > 500 else ''}\n"
                
                if include_images and result.get('images'):
                    formatted_output += f"   Images: {len(result['images'])} found\n"
                
                formatted_output += "\n"
        
        # Show failed extractions
        if response.get('failed_results'):
            formatted_output += "❌ Failed Extractions:\n"
            for failed in response['failed_results']:
                formatted_output += f"   • {failed.get('url', 'Unknown URL')}: {failed.get('error', 'Unknown error')}\n"
        
        return f"✅ Content extraction completed. {len(response.get('results', []))} successful, {len(response.get('failed_results', []))} failed.", {
            "formatted_output": formatted_output,
            "raw_response": response
        }
        
    except Exception as e:
        return f"❌ Tavily extraction error: {str(e)}", {}

def tavily_get_search_context(
    query: str,
    search_depth: str = "basic",
    max_results: int = 5,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> Tuple[str, str]:
    """
    Get search context for RAG applications using Tavily API.
    Returns a context string ready to be fed into RAG applications.
    
    Args:
        query: Search query string
        search_depth: "basic" or "advanced" search depth
        max_results: Maximum number of results (1-20, default: 5)
        include_domains: List of domains to include (optional)
        exclude_domains: List of domains to exclude (optional)
        
    Returns:
        Tuple[str, str]: (status_message, context_string)
    """
    try:
        # Import Tavily client
        try:
            import tavily
            TavilyClient = tavily.TavilyClient
        except ImportError:
            return "❌ Error: Tavily library not installed. Run: pip install tavily-python", ""
        
        # Get API key from environment
        api_key = os.getenv("TVLY_API_KEY")
        if not api_key:
            return "❌ Error: TVLY_API_KEY environment variable not set", ""
        
        # Initialize client
        client = TavilyClient(api_key=api_key)
        
        # Prepare search parameters
        search_params = {
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results
        }
        
        if include_domains:
            search_params["include_domains"] = include_domains
        if exclude_domains:
            search_params["exclude_domains"] = exclude_domains
        
        # Get search context
        context = client.get_search_context(**search_params)
        
        return f"✅ Generated search context for query: '{query}' ({len(context)} characters)", context
        
    except Exception as e:
        return f"❌ Tavily context generation error: {str(e)}", ""

def tavily_qna_search(
    query: str,
    search_depth: str = "advanced",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> Tuple[str, str]:
    """
    Get a direct answer to a question using Tavily's Q&A search.
    
    Args:
        query: Question to ask
        search_depth: "basic" or "advanced" search depth (default: advanced for Q&A)
        include_domains: List of domains to include (optional)
        exclude_domains: List of domains to exclude (optional)
        
    Returns:
        Tuple[str, str]: (status_message, answer)
    """
    try:
        # Import Tavily client
        try:
            import tavily
            TavilyClient = tavily.TavilyClient
        except ImportError:
            return "❌ Error: Tavily library not installed. Run: pip install tavily-python", ""
        
        # Get API key from environment
        api_key = os.getenv("TVLY_API_KEY")
        if not api_key:
            return "❌ Error: TVLY_API_KEY environment variable not set", ""
        
        # Initialize client
        client = TavilyClient(api_key=api_key)
        
        # Prepare search parameters
        search_params = {
            "query": query,
            "search_depth": search_depth
        }
        
        if include_domains:
            search_params["include_domains"] = include_domains
        if exclude_domains:
            search_params["exclude_domains"] = exclude_domains
        
        # Get Q&A answer
        answer = client.qna_search(**search_params)
        
        return f"✅ Generated answer for: '{query}'", answer
        
    except Exception as e:
        return f"❌ Tavily Q&A error: {str(e)}", ""

def tavily_research_assistant(
    query: str,
    search_type: str = "web_search",
    search_depth: str = "basic",
    max_results: int = 5,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> Tuple[str, str]:
    """
    Research assistant tool for AI agents to gather current information for creative writing.
    Returns clean, usable content that agents can immediately incorporate into their writings.
    
    Args:
        query: What to research (e.g., "latest developments in AI poetry", "current events in Gaza")
        search_type: "web_search", "qna_search", or "context_search"
        search_depth: "basic" or "advanced" (advanced recommended for creative writing)
        max_results: Maximum results for web search (1-10, default: 5)
        include_domains: List of domains to include (e.g., ["wikipedia.org", "reuters.com"])
        exclude_domains: List of domains to exclude (e.g., ["reddit.com", "twitter.com"])
        
    Returns:
        Tuple[str, str]: (status_message, research_content)
        
    Usage for AI Agents:
        - Use web_search for broad research and current events
        - Use qna_search for specific factual questions  
        - Use context_search for background information on topics
    """
    try:
        # Perform the appropriate search
        if search_type == "web_search":
            status, result_data = tavily_web_search(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                include_answer=True,
                include_raw_content=False,  # Keep it clean for agents
                include_domains=include_domains,
                exclude_domains=exclude_domains
            )
            
            if not status.startswith("✅"):
                return status, ""
            
            # Extract clean, usable content for agents
            raw_response = result_data.get("raw_response", {})
            research_content = f"Research Results for: {query}\n\n"
            
            # Include AI answer if available
            if raw_response.get('answer'):
                research_content += f"Key Insight: {raw_response['answer']}\n\n"
            
            # Include top results with clean formatting
            research_content += "Current Information:\n"
            for i, result in enumerate(raw_response.get('results', [])[:3], 1):  # Top 3 for focus
                research_content += f"{i}. {result.get('title', 'Untitled')}\n"
                if result.get('content'):
                    # Clean and truncate content for creative use
                    clean_content = result['content'].replace('\n', ' ').strip()
                    if len(clean_content) > 300:
                        clean_content = clean_content[:300] + "..."
                    research_content += f"   {clean_content}\n"
                research_content += f"   Source: {result.get('url', 'Unknown')}\n\n"
            
            return f"✅ Research completed: Found current information about '{query}'", research_content
            
        elif search_type == "qna_search":
            status, answer = tavily_qna_search(
                query=query,
                search_depth=search_depth,
                include_domains=include_domains,
                exclude_domains=exclude_domains
            )
            
            if not status.startswith("✅"):
                return status, ""
            
            research_content = f"Research Question: {query}\n\nAnswer: {answer}\n\n"
            research_content += "This information is current and can be used as factual reference in your writing."
            
            return f"✅ Research completed: Got direct answer for '{query}'", research_content
            
        elif search_type == "context_search":
            status, context = tavily_get_search_context(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                include_domains=include_domains,
                exclude_domains=exclude_domains
            )
            
            if not status.startswith("✅"):
                return status, ""
            
            research_content = f"Background Context: {query}\n\n{context}\n\n"
            research_content += "This context provides comprehensive background information for creative writing purposes."
            
            return f"✅ Research completed: Generated background context for '{query}'", research_content
            
        else:
            return "❌ Error: Invalid search_type. Use 'web_search', 'qna_search', or 'context_search'", ""
            
    except Exception as e:
        return f"❌ Research error: {str(e)}", ""
