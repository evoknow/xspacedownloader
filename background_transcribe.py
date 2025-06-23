#!/usr/bin/env python3
# background_transcribe.py - Background process for speech-to-text transcription

import os
import sys
import json
import time
import signal
import logging
import argparse
import traceback
import threading
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/transcription.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('background_transcribe')

# Add parent directory to path for importing components
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file
try:
    from load_env import load_env
    load_env()
    logger.info("Environment variables loaded from .env file")
except ImportError:
    logger.warning("load_env module not found - using system environment variables only")
except Exception as e:
    logger.warning(f"Error loading .env file: {e}")

# Import components
try:
    from components.SpeechToText import SpeechToText
    from components.AICost import AICost
except ImportError as e:
    logger.error(f"Failed to import required components: {e}")
    sys.exit(1)

def check_existing_transcript(space_id, language):
    """
    Check if a transcript already exists for the given space and language.
    
    Args:
        space_id (str): The space ID
        language (str): The language code
        
    Returns:
        dict: Existing transcript data or None
    """
    import mysql.connector
    connection = None
    cursor = None
    
    try:
        # Load database config
        with open("db_config.json", 'r') as f:
            config = json.load(f)
        
        db_config = config["mysql"].copy()
        if 'use_ssl' in db_config:
            del db_config['use_ssl']
        
        # Connect to database
        connection = mysql.connector.connect(
            host=db_config.get('host'),
            port=db_config.get('port', 3306),
            database=db_config.get('database'),
            user=db_config.get('user'),
            password=db_config.get('password'),
            charset='utf8mb4',
            use_unicode=True,
            autocommit=False,
            connect_timeout=30
        )
        
        cursor = connection.cursor(dictionary=True)
        
        # First try exact match
        query = "SELECT * FROM space_transcripts WHERE space_id = %s AND language = %s"
        cursor.execute(query, (space_id, language))
        result = cursor.fetchone()
        
        # If no exact match and language has locale, try base language
        if not result and '-' in language:
            base_language = language.split('-')[0]
            query = "SELECT * FROM space_transcripts WHERE space_id = %s AND language LIKE %s"
            cursor.execute(query, (space_id, f"{base_language}-%"))
            result = cursor.fetchone()
        
        return result
        
    except Exception as e:
        logger.error(f"Error checking existing transcript: {e}")
        return None
    finally:
        # Always close cursor and connection
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if connection:
            try:
                connection.close()
            except:
                pass


def generate_and_save_tags_with_ai(space_id, transcript_text):
    """
    Generate tags from transcript using AI and save them to database.
    
    Args:
        space_id (str): The space ID
        transcript_text (str): The transcript text
    """
    try:
        # Use the Space component's generate_tags_from_transcript method
        # which has proper logging to tag.log
        logger.info(f"Generating tags for space {space_id} using Space component")
        
        from components.Space import Space
        space = Space()
        
        # Generate tags using the Space component method (which includes logging to tag.log)
        tags = space.generate_tags_from_transcript(transcript_text, max_tags=8)
        
        if tags:
            logger.info(f"Successfully generated {len(tags)} tags for space {space_id}: {tags}")
            save_tags_to_database(space_id, tags)
        else:
            logger.warning(f"No tags generated for space {space_id}")
            
        return  # Exit early since we're using the Space component
        
        # Keep the old code below as backup (but it won't be reached)
        # Try to use AI for tag generation
        ai_config_exists = False
        
        try:
            with open("mainconfig.json", 'r') as f:
                main_config = json.load(f)
                
            # Check if AI is configured
            ai_config = main_config.get('ai', {})
            if ai_config.get('provider'):
                ai_config_exists = True
        except:
            pass
        
        if ai_config_exists:
            try:
                # Import AI component
                if ai_config['provider'] == 'openai':
                    from components.OpenAI import OpenAI
                    import os
                    api_key = os.environ.get('OPENAI_API_KEY') or ai_config.get('openai', {}).get('api_key')
                    model = ai_config.get('openai', {}).get('model', 'gpt-4o-mini')
                    
                    if api_key:
                        logger.info(f"Using OpenAI for tag generation with model: {model}")
                        ai = OpenAI(api_key, model=model)
                        
                        # Prepare prompt for tag generation using user's clean prompt
                        prompt = f"""Extract up to 10 meaningful tags from this transcript. 

IMPORTANT RULES:
1. NO COMMON WORDS like: going, because, think, about, would, doesn't, really, maybe, probably, something, could, should, might, actually, basically
2. INCLUDE: Countries, cities, places, regions mentioned (e.g., Bangladesh, New York, Silicon Valley)
3. INCLUDE: Specific topics discussed (e.g., cybersecurity, climate change, artificial intelligence)
4. INCLUDE: Organizations, companies, or institutions mentioned
5. INCLUDE: Technical terms, industries, or fields discussed
6. Only include words/phrases that someone would search for to find this specific content

Return ONLY a JSON array of keywords. Example: ["Bangladesh", "cybersecurity", "data breach", "Dhaka", "IT industry"]

Transcript:
{transcript_text[:3000]}..."""

                        messages = [
                            {"role": "system", "content": "You are a helpful assistant that extracts topic tags from transcripts."},
                            {"role": "user", "content": prompt}
                        ]
                        
                        success, response = ai._make_request(messages, max_tokens=150, temperature=0.3)
                        
                        # Track AI cost for tag generation
                        if success and isinstance(response, dict) and 'usage' in response:
                            try:
                                ai_cost = AICost()
                                usage = response['usage']
                                input_tokens = usage.get('input_tokens', 0)
                                output_tokens = usage.get('output_tokens', 0)
                                
                                # Track cost
                                ai_cost.track_cost(
                                    space_id=space_id,
                                    action='tag_generation',
                                    vendor='openai',
                                    model=ai.model,  # Use the model from AI component
                                    input_tokens=input_tokens,
                                    output_tokens=output_tokens
                                )
                                logger.info(f"Tracked AI cost for tag generation: {input_tokens} input + {output_tokens} output tokens")
                            except Exception as cost_error:
                                logger.warning(f"Failed to track AI cost for tag generation: {cost_error}")
                        
                        if success:
                            try:
                                # Extract content from response
                                content = response.get('content', '') if isinstance(response, dict) else str(response)
                                
                                # Parse tags - AI returns comma-separated string
                                if isinstance(content, str) and content.strip():
                                    # Split by comma and clean up each tag
                                    tags = [tag.strip() for tag in content.split(',') if tag.strip()]
                                    
                                    if len(tags) > 0:
                                        logger.info(f"AI generated {len(tags)} tags for space {space_id}: {tags}")
                                        
                                        # Save tags using Tag component
                                        save_tags_to_database(space_id, tags)
                                        return
                                else:
                                    logger.warning("AI response was not a valid string")
                            except Exception as e:
                                logger.warning(f"Failed to parse AI response: {e}, falling back to keyword extraction")
                        else:
                            logger.warning(f"AI tag generation failed: {response}")
                            
                elif ai_config['provider'] == 'claude':
                    from components.Claude import Claude
                    import os
                    api_key = os.environ.get('ANTHROPIC_API_KEY') or ai_config.get('claude', {}).get('api_key')
                    model = ai_config.get('claude', {}).get('model', 'claude-3-haiku-20240307')
                    
                    if api_key:
                        logger.info(f"Using Claude for tag generation with model: {model}")
                        ai = Claude(api_key, model=model)
                        
                        # Same clean prompt for Claude
                        prompt = f"""Extract up to 10 meaningful tags from this transcript. 

IMPORTANT RULES:
1. NO COMMON WORDS like: going, because, think, about, would, doesn't, really, maybe, probably, something, could, should, might, actually, basically
2. INCLUDE: Countries, cities, places, regions mentioned (e.g., Bangladesh, New York, Silicon Valley)
3. INCLUDE: Specific topics discussed (e.g., cybersecurity, climate change, artificial intelligence)
4. INCLUDE: Organizations, companies, or institutions mentioned
5. INCLUDE: Technical terms, industries, or fields discussed
6. Only include words/phrases that someone would search for to find this specific content

Return ONLY a JSON array of keywords. Example: ["Bangladesh", "cybersecurity", "data breach", "Dhaka", "IT industry"]

Transcript:
{transcript_text[:3000]}..."""

                        success, response = ai.summary(prompt, max_length=150)
                        
                        if success:
                            try:
                                # Try to extract JSON from response
                                import re
                                json_match = re.search(r'\[.*?\]', response)
                                if json_match:
                                    tags = json.loads(json_match.group())
                                    if isinstance(tags, list) and len(tags) > 0:
                                        logger.info(f"AI generated {len(tags)} tags for space {space_id}: {tags}")
                                        save_tags_to_database(space_id, tags)
                                        return
                            except:
                                logger.warning("Failed to parse Claude response, falling back to keyword extraction")
                                
            except Exception as e:
                logger.warning(f"AI tag generation error: {e}, falling back to keyword extraction")
                
        # Fall back to keyword extraction if AI is not available or fails
        logger.info("Using keyword extraction for tag generation")
        generate_and_save_tags(space_id, transcript_text)
        
    except Exception as e:
        logger.error(f"Error in AI tag generation: {e}", exc_info=True)
        # Fall back to keyword extraction
        generate_and_save_tags(space_id, transcript_text)


def save_tags_to_database(space_id, tags):
    """Helper function to save tags to database."""
    try:
        # Import Tag component
        from components.Tag import Tag
        
        # Save tags to database
        import mysql.connector
        connection = None
        
        with open("db_config.json", 'r') as f:
            config = json.load(f)
        
        db_config = config["mysql"].copy()
        if 'use_ssl' in db_config:
            del db_config['use_ssl']
        
        connection = mysql.connector.connect(**db_config)
        
        # Use Tag component for proper tag handling
        tag_component = Tag(connection)
        
        # Add tags to space using the Tag component's method
        added_count = tag_component.add_tags_to_space(space_id, tags, user_id=0)
        
        logger.info(f"Successfully saved {added_count} tags for space {space_id}")
        
    except Exception as e:
        logger.error(f"Error saving tags to database: {e}")
    finally:
        if connection and connection.is_connected():
            connection.close()


def generate_and_save_tags(space_id, transcript_text):
    """
    Generate topic-focused tags from transcript using improved keyword extraction.
    
    Args:
        space_id (str): The space ID
        transcript_text (str): The transcript text
    """
    try:
        import re
        from collections import Counter
        
        logger.info(f"Generating tags for space {space_id} using topic-focused extraction")
        
        # Topic-focused tag extraction 
        # Focus on: business terms, technology, concepts, subjects, NOT conversation
        
        # Step 1: Extract potential topic phrases and compound terms
        text = transcript_text.lower()
        
        # Common business/technology/subject terms (these are GOOD for tags)
        topic_keywords = {
            # Business terms
            'business', 'sales', 'marketing', 'strategy', 'revenue', 'profit', 'growth',
            'customer', 'client', 'service', 'product', 'brand', 'market', 'industry',
            'company', 'startup', 'entrepreneur', 'investment', 'finance', 'budget',
            'leadership', 'management', 'team', 'project', 'development', 'innovation',
            'competition', 'analysis', 'planning', 'operations', 'logistics',
            
            # Technology terms
            'technology', 'software', 'hardware', 'platform', 'system', 'application',
            'digital', 'online', 'internet', 'website', 'mobile', 'cloud', 'data',
            'analytics', 'algorithm', 'automation', 'programming', 'coding', 'development',
            'artificial', 'intelligence', 'machine', 'learning', 'cybersecurity', 'security',
            'blockchain', 'cryptocurrency', 'bitcoin', 'ethereum', 'nft', 'metaverse',
            
            # Subject areas
            'education', 'health', 'medicine', 'science', 'research', 'psychology',
            'philosophy', 'politics', 'economics', 'finance', 'environment', 'climate',
            'energy', 'sustainability', 'transportation', 'communication', 'media',
            'entertainment', 'sports', 'fitness', 'nutrition', 'travel', 'culture',
            'art', 'music', 'literature', 'history', 'geography', 'language'
        }
        
        # Book/Product titles and proper nouns (keep capitalization)
        proper_nouns = re.findall(r'\b[A-Z][a-z]*(?:\s+[A-Z][a-z]*){0,3}\b', transcript_text)
        
        # Filter proper nouns to likely be topics (not just names)
        topic_proper_nouns = []
        for noun in proper_nouns:
            noun_lower = noun.lower()
            # Include if it contains topic keywords or seems like a title/concept
            if (any(keyword in noun_lower for keyword in topic_keywords) or
                len(noun.split()) > 1 or  # Multi-word terms likely topics
                any(word in noun_lower for word in ['edge', 'guide', 'system', 'method', 'strategy', 'solution'])):
                topic_proper_nouns.append(noun)
        
        # Step 2: Extract compound terms (e.g., "artificial intelligence", "machine learning")
        compound_terms = []
        words = text.split()
        
        for i in range(len(words) - 1):
            word1, word2 = words[i], words[i + 1]
            compound = f"{word1} {word2}"
            
            # Include if both words are topic-related
            if (word1 in topic_keywords and word2 in topic_keywords) or \
               (any(keyword in compound for keyword in ['artificial intelligence', 'machine learning', 
                    'cyber security', 'data science', 'digital marketing', 'social media',
                    'user experience', 'content marketing', 'email marketing', 'search engine'])):
                compound_terms.append(compound)
        
        # Step 3: Extract single topic words that appear frequently
        topic_words = []
        word_freq = Counter(re.findall(r'\b[a-z]{4,}\b', text))
        
        for word, count in word_freq.most_common(50):
            if count >= 2 and word in topic_keywords:
                topic_words.append(word)
        
        # Step 4: Look for book/product mentions specifically 
        book_patterns = [
            r'book\s+called\s+([A-Z][A-Za-z\s]{5,25})',  # "book called The AI Edge"
            r'called\s+([A-Z][A-Za-z\s]{5,25})',  # "called The Sales Strategy"
            r'\bthe\s+([A-Z][A-Z\s]{2,15})\b',  # "the AI EDGE" (all caps titles)
        ]
        
        book_mentions = []
        for pattern in book_patterns:
            matches = re.findall(pattern, transcript_text)
            for match in matches:
                match = match.strip()
                # Clean up the match - remove trailing words that don't belong
                words = match.split()
                clean_words = []
                for word in words:
                    # Stop at common non-title words
                    if word.lower() in ['and', 'the', 'is', 'are', 'was', 'were', 'on', 'at', 'by', 'to', 'of', 'that', 'this', 'we', 'it']:
                        if len(clean_words) == 0:  # Skip leading articles
                            continue
                        else:  # Stop at trailing articles/connectors
                            break
                    clean_words.append(word)
                
                if len(clean_words) >= 2 and len(clean_words) <= 4:  # 2-4 word titles
                    clean_match = ' '.join(clean_words)
                    if clean_match not in book_mentions:
                        book_mentions.append(clean_match)
        
        # Step 5: Combine and rank all candidates
        all_candidates = []
        
        # Add proper nouns (high priority)
        for noun in topic_proper_nouns[:5]:
            all_candidates.append((noun, 3))
        
        # Add compound terms (high priority)
        compound_freq = Counter(compound_terms)
        for term, count in compound_freq.most_common(5):
            all_candidates.append((term, count * 2))
        
        # Add book mentions (high priority)
        for book in book_mentions[:3]:
            all_candidates.append((book, 4))
        
        # Add single topic words (medium priority)
        for word in topic_words[:8]:
            all_candidates.append((word, word_freq[word]))
        
        # Step 6: Final selection and cleanup
        seen = set()
        final_tags = []
        
        # Sort by priority score
        all_candidates.sort(key=lambda x: x[1], reverse=True)
        
        for candidate, score in all_candidates:
            candidate_clean = candidate.strip().lower()
            
            # Skip duplicates and very short terms
            if candidate_clean in seen or len(candidate_clean) < 3:
                continue
            
            # Skip low-quality phrases (those containing too many stop words)
            words_in_candidate = candidate_clean.split()
            stop_word_ratio = sum(1 for word in words_in_candidate if word in ['the', 'and', 'of', 'to', 'that', 'this', 'we', 'are', 'is', 'was', 'were', 'actually']) / len(words_in_candidate)
            if stop_word_ratio > 0.5:  # More than half stop words
                continue
            
            # Skip phrases that end with common connecting words
            if candidate_clean.endswith((' and', ' of', ' to', ' that', ' this', ' we', ' are', ' is', ' was', ' were', ' actually')):
                continue
            
            # Skip if it's just a subset of existing tag
            is_subset = False
            for existing in final_tags:
                if candidate_clean in existing.lower() or existing.lower() in candidate_clean:
                    is_subset = True
                    break
            
            if not is_subset:
                final_tags.append(candidate)
                seen.add(candidate_clean)
                
            if len(final_tags) >= 8:  # Limit to 8 high-quality tags
                break
        
        # If we have very few tags, this might be a very conversational transcript
        if len(final_tags) < 3:
            logger.warning(f"Only found {len(final_tags)} topic tags for space {space_id}, transcript may be too conversational")
            # Add a generic tag based on any business terms found
            if any(word in text for word in ['sales', 'business', 'market']):
                final_tags.append('business discussion')
            elif any(word in text for word in ['technology', 'tech', 'software', 'digital']):
                final_tags.append('technology discussion')
            else:
                final_tags.append('general discussion')
        
        tags = final_tags
        
        if tags:
            logger.info(f"Generated {len(tags)} topic-focused tags for space {space_id}: {tags}")
            save_tags_to_database(space_id, tags)
        else:
            logger.warning(f"No meaningful tags generated for space {space_id}")
                    
    except Exception as e:
        logger.error(f"Error generating tags: {e}", exc_info=True)


def save_transcript_to_db(space_id, transcript_text, language="en-US"):
    """
    Standalone function to save transcript to database.
    Creates its own database connection, uses it, and closes it.
    
    Args:
        space_id (str): The space ID
        transcript_text (str): The transcript content
        language (str): The language code
        
    Returns:
        int: Transcript ID if successful, None otherwise
    """
    import mysql.connector
    connection = None
    cursor = None
    
    try:
        # Load database config
        with open("db_config.json", 'r') as f:
            config = json.load(f)
        
        db_config = config["mysql"].copy()
        if 'use_ssl' in db_config:
            del db_config['use_ssl']
        
        # Connect to database
        connection = mysql.connector.connect(
            host=db_config.get('host'),
            port=db_config.get('port', 3306),
            database=db_config.get('database'),
            user=db_config.get('user'),
            password=db_config.get('password'),
            charset='utf8mb4',
            use_unicode=True,
            autocommit=False,
            connect_timeout=30
        )
        
        cursor = connection.cursor()
        
        # Check if transcript exists
        check_query = """
        SELECT id FROM space_transcripts 
        WHERE space_id = %s AND language = %s
        """
        cursor.execute(check_query, (space_id, language))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing
            update_query = """
            UPDATE space_transcripts 
            SET transcript = %s, updated_at = NOW()
            WHERE id = %s
            """
            cursor.execute(update_query, (transcript_text, existing[0]))
            connection.commit()
            return existing[0]
        else:
            # Insert new
            insert_query = """
            INSERT INTO space_transcripts 
            (space_id, language, transcript, created_at) 
            VALUES (%s, %s, %s, NOW())
            """
            cursor.execute(insert_query, (space_id, language, transcript_text))
            connection.commit()
            return cursor.lastrowid
            
    except Exception as e:
        logger.error(f"Error saving transcript to database: {e}")
        if connection:
            try:
                connection.rollback()
            except:
                pass
        return None
    finally:
        # Always close cursor and connection
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if connection:
            try:
                connection.close()
            except:
                pass


class TranscriptionWorker:
    """Background worker for handling transcription tasks."""
    
    def __init__(self, status_dir='./transcript_jobs'):
        """
        Initialize the transcription worker.
        
        Args:
            status_dir (str): Directory to store transcription job status files
        """
        self.status_dir = Path(status_dir)
        self.status_dir.mkdir(parents=True, exist_ok=True)
        self.stt = None
        self.running = True
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        
        logger.info(f"Transcription worker initialized. Status directory: {self.status_dir}")
    
    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}. Shutting down gracefully...")
        self.running = False
    
    def check_job_cancellation(self, job_id):
        """
        Check if a job has been cancelled by reading its status file.
        
        Args:
            job_id (str): The job ID to check
            
        Returns:
            bool: True if job is cancelled, False otherwise
        """
        try:
            job_file = self.status_dir / f"{job_id}.json"
            if not job_file.exists():
                return False
                
            with open(job_file, 'r') as f:
                job_data = json.load(f)
                
            status = job_data.get('status', '')
            if status == 'cancelled':
                logger.info(f"Job {job_id} detected as cancelled")
                return True
                
            # Also check for cancellation signal files created by admin
            signal_file = Path(f'./temp/cancel_{job_id}.signal')
            if signal_file.exists():
                logger.info(f"Job {job_id} cancellation signal file detected")
                # Update job status to cancelled
                self.update_job_status(job_id, 'cancelled', error='Job cancelled by admin')
                # Remove signal file
                try:
                    signal_file.unlink()
                except:
                    pass
                return True
                
            return False
            
        except Exception as e:
            logger.warning(f"Error checking cancellation for job {job_id}: {e}")
            return False
    
    def load_speech_to_text(self, model_name='tiny'):
        """
        Load the SpeechToText component with the specified model.
        
        Args:
            model_name (str): The Whisper model to load (tiny, base, small, medium, large)
            
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        if self.stt is None or self.stt.model_name != model_name:
            try:
                logger.info(f"Loading SpeechToText model: {model_name}")
                self.stt = SpeechToText(model_name=model_name)
                return True
            except Exception as e:
                logger.error(f"Failed to load SpeechToText: {e}")
                return False
        return True
    
    def create_job(self, space_id, language='en-US', model='base', detect_language=False, 
                  translate_to=None, callback_url=None):
        """
        Create a transcription job.
        
        Args:
            space_id (str): The space ID to transcribe
            language (str): Language code for transcription
            model (str): Whisper model to use
            detect_language (bool): Whether to detect language automatically
            translate_to (str): Language code to translate to
            callback_url (str): URL to call when job completes
            
        Returns:
            str: Job ID
        """
        logger.info(f"Creating transcription job for space {space_id} with model {model}")
        
        job_id = f"{space_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        job_data = {
            'job_id': job_id,
            'space_id': space_id,
            'language': language,
            'model': model,
            'detect_language': detect_language,
            'translate_to': translate_to,
            'callback_url': callback_url,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'progress': 0,
            'result': None,
            'error': None
        }
        
        # Save job data to file
        job_file_path = self.status_dir / f"{job_id}.json"
        
        with open(job_file_path, 'w') as f:
            json.dump(job_data, f, indent=4)
        
        logger.info(f"Created transcription job {job_id} for space {space_id}")
            
        return job_id
    
    def update_job_status(self, job_id, status, progress=None, result=None, error=None):
        """
        Update job status.
        
        Args:
            job_id (str): The job ID
            status (str): New status (pending, processing, completed, failed)
            progress (float, optional): Progress percentage (0-100)
            result (dict, optional): Result data if completed
            error (str, optional): Error message if failed
        """
        job_file = self.status_dir / f"{job_id}.json"
        
        if not job_file.exists():
            logger.error(f"Job file not found: {job_file}")
            return False
        
        try:
            with open(job_file, 'r') as f:
                job_data = json.load(f)
            
            job_data['status'] = status
            job_data['updated_at'] = datetime.now().isoformat()
            
            if progress is not None:
                job_data['progress'] = progress
            
            if result is not None:
                job_data['result'] = result
            
            if error is not None:
                job_data['error'] = error
            
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=4)
            
            return True
        except Exception as e:
            logger.error(f"Error updating job status: {e}")
            return False
    
    def get_job_status(self, job_id):
        """
        Get job status.
        
        Args:
            job_id (str): The job ID
            
        Returns:
            dict: Job status data or None if not found
        """
        job_file = self.status_dir / f"{job_id}.json"
        
        if not job_file.exists():
            logger.error(f"Job file not found: {job_file}")
            return None
        
        try:
            with open(job_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading job status: {e}")
            return None
    
    def get_pending_jobs(self):
        """
        Get all pending jobs.
        
        Returns:
            list: List of pending job data
        """
        pending_jobs = []
        
        try:
            json_files = list(self.status_dir.glob('*.json'))
            
            for job_file in json_files:
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                        
                    status = job_data.get('status', 'unknown')
                    
                    if status == 'pending':
                        pending_jobs.append(job_data)
                        
                except Exception as e:
                    logger.error(f"Error reading job file {job_file}: {e}")
                    
        except Exception as e:
            logger.error(f"Error listing directory: {e}")
        
        return pending_jobs
    
    def process_job(self, job_data):
        """
        Process a transcription job.
        
        Args:
            job_data (dict): Job data
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Handle both 'job_id' and 'id' field names for backward compatibility
        job_id = job_data.get('job_id') or job_data.get('id')
        space_id = job_data.get('space_id')
        
        if not space_id:
            logger.error(f"Job {job_id} missing required space_id field")
            self.update_job_status(job_id, 'failed', error="Missing space_id field")
            return False
        
        try:
            # Update job status to processing
            self.update_job_status(job_id, 'processing', progress=5)
            
            # Check for cancellation after status update
            if self.check_job_cancellation(job_id):
                logger.info(f"Job {job_id} cancelled during setup")
                return False
            
            # Note: We no longer need a Space instance during transcription
            # Database operations will be done after transcription completes
            
            # Load the right model
            # Handle both direct 'model' field and nested in 'options'
            model = job_data.get('model') or job_data.get('options', {}).get('model', 'tiny')
            
            if not self.load_speech_to_text(model_name=model):
                logger.error(f"Failed to load model: {model}")
                self.update_job_status(job_id, 'failed', error=f"Failed to load model: {model}")
                return False
            
            # Update progress
            self.update_job_status(job_id, 'processing', progress=10)
            
            # Find the audio file - load config directly
            try:
                with open('mainconfig.json', 'r') as f:
                    config = json.load(f)
                download_dir = config.get('download_dir', './downloads')
            except Exception as e:
                logger.warning(f"Failed to load mainconfig.json: {e}")
                download_dir = './downloads'
                
            audio_path = None
            
            for ext in ['mp3', 'm4a', 'wav']:
                file_path = os.path.join(download_dir, f"{space_id}.{ext}")
                
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    
                    if file_size > 0:
                        audio_path = file_path
                        break
            
            if not audio_path:
                logger.error(f"No audio file found for space {space_id} in {download_dir}")
                self.update_job_status(job_id, 'failed', error=f"Audio file not found for space {space_id}")
                return False
            
            # Update progress
            self.update_job_status(job_id, 'processing', progress=15)
            
            # Set up transcription options
            # Handle both direct fields and nested in 'options'
            job_options = job_data.get('options', {})
            
            language = job_data.get('language') or job_options.get('language', 'en-US')
            detect_language = job_data.get('detect_language', job_options.get('detect_language', False))
            translate_to = job_data.get('translate_to', job_options.get('translate_to'))
            include_timecodes = job_data.get('include_timecodes', job_options.get('include_timecodes', True))
            
            options = {
                'language': language,
                'detect_language': detect_language,
                'verbose': True,
                'include_timecodes': include_timecodes
            }
            
            if translate_to:
                options['translate_to'] = translate_to
            
            # Check if transcript already exists in database before processing
            target_language = translate_to if translate_to else language
            if target_language and len(target_language) == 2:
                target_language = f"{target_language}-{target_language.upper()}"
            
            # Check database for existing transcript using standalone function
            existing_transcript = None
            overwrite_option = job_options.get('overwrite', True)
            
            if not overwrite_option:
                existing_transcript = check_existing_transcript(space_id, target_language)
                
                if existing_transcript:
                    logger.info(f"Found existing transcript for {space_id} in {existing_transcript['language']}, skipping AI processing")
                    
                    # Build result data from existing transcript
                    result_data = {
                        "transcript_id": existing_transcript['id'],
                        "space_id": space_id,
                        "language": existing_transcript['language'],
                        "text_sample": existing_transcript['transcript'][:500] + "..." if len(existing_transcript['transcript']) > 500 else existing_transcript['transcript'],
                        "from_database": True
                    }
                    
                    # Mark job as completed without AI processing
                    self.update_job_status(job_id, 'completed', progress=100, result=result_data)
                    logger.info(f"Transcription job {job_id} completed using existing database transcript")
                    return True
            
            # Perform transcription using AI
            logger.info(f"Processing transcription with AI for {space_id} in {target_language}")
            
            # Start transcription with progress tracking
            import threading
            import time
            
            # Get audio file size and estimate duration
            audio_file_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
            logger.info(f"Audio file size: {audio_file_size / 1024 / 1024:.1f} MB")
            
            # Estimate audio duration from file size (rough estimate for MP3)
            # MP3 at ~128kbps: 1MB ≈ 1 minute of audio
            estimated_audio_minutes = max(1, (audio_file_size / 1024 / 1024))
            logger.info(f"Estimated audio duration: {estimated_audio_minutes:.1f} minutes")
            
            # Estimate processing time based on file size (rough estimate)
            # Typically ~1-2 minutes per MB for base model
            estimated_seconds = max(30, (audio_file_size / 1024 / 1024) * 60)  # Min 30 seconds
            logger.info(f"Estimated processing time: {estimated_seconds:.0f} seconds")
            
            # Update job status with estimated audio duration
            self.update_job_status(job_id, 'processing', progress=15, 
                                 result={'estimated_audio_minutes': estimated_audio_minutes})
            
            # Start progress tracking thread
            transcription_complete = threading.Event()
            
            def update_progress_during_transcription():
                """Update progress periodically during transcription."""
                start_time = time.time()
                while not transcription_complete.is_set():
                    elapsed = time.time() - start_time
                    progress_ratio = min(elapsed / estimated_seconds, 0.9)  # Cap at 90%
                    progress = int(15 + (progress_ratio * 65))  # 15% to 80%
                    
                    # Include audio duration info in progress updates
                    progress_result = {
                        'estimated_audio_minutes': estimated_audio_minutes,
                        'processing_elapsed_seconds': elapsed
                    }
                    self.update_job_status(job_id, 'processing', progress=progress, result=progress_result)
                    logger.info(f"Transcription progress: {progress}% (elapsed: {elapsed:.0f}s, ~{estimated_audio_minutes:.1f} min audio)")
                    
                    # Update every 30 seconds
                    if transcription_complete.wait(30):
                        break
            
            # Start progress thread
            progress_thread = threading.Thread(target=update_progress_during_transcription)
            progress_thread.daemon = True
            progress_thread.start()
            
            # Write job progress to temp file instead of database
            temp_dir = self.status_dir / "temp"
            temp_dir.mkdir(exist_ok=True)
            temp_file = temp_dir / f"{job_id}_result.json"
            
            try:
                # Log transcription start
                import time
                transcription_start_time = time.time()
                
                # Final check for cancellation before expensive transcription operation
                if self.check_job_cancellation(job_id):
                    logger.info(f"Job {job_id} cancelled before transcription")
                    return False
                
                # Perform the actual transcription - NO DATABASE CONNECTION NEEDED
                result = self.stt.transcribe(audio_path, **options)
                
                transcription_end_time = time.time()
                transcription_duration = transcription_end_time - transcription_start_time
                logger.info(f"Transcription completed in {transcription_duration:.1f} seconds")
                
                # Track cost for AI transcription if using OpenAI
                try:
                    user_id = job_data.get('user_id')
                    
                    # Track costs if user_id is available
                    if user_id and user_id > 0:
                        # Check if this was an OpenAI transcription
                        model_used = job_data.get('model', 'tiny')
                        stt_provider = getattr(self.stt, 'provider', 'local')
                        
                        if stt_provider == 'openai':
                            ai_cost = AICost()
                            
                            # Determine tokens based on whether we have usage data
                            if hasattr(result, 'get') and result.get('usage'):
                                # OpenAI transcription with usage data
                                usage = result['usage']
                                input_tokens = usage.get('input_tokens', 0)
                                output_tokens = usage.get('output_tokens', 0)
                            else:
                                # Estimate tokens for OpenAI transcription
                                transcript_text = result.get('text', '') if isinstance(result, dict) else str(result)
                                input_tokens, output_tokens = ai_cost.estimate_transcription_tokens(
                                    transcription_duration, len(transcript_text)
                                )
                            
                            # Track cost using unified AICost component
                            success, message, cost = ai_cost.track_cost(
                                space_id=space_id,
                                action='transcription',
                                vendor='openai',
                                model=getattr(self.stt, 'model_name', 'gpt-4o-mini-transcribe'),
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                user_id=user_id,
                                cookie_id=None,
                                deduct_credits=True
                            )
                            
                            if success:
                                logger.info(f"COST TRACKING: {message} - ${cost:.2f} for {input_tokens}+{output_tokens} tokens")
                            else:
                                logger.warning(f"COST TRACKING: {message}")
                        else:
                            logger.info(f"Skipping cost tracking for local transcription model: {model_used}")
                    else:
                        logger.info("Skipping cost tracking - no valid user_id provided")
                        
                except Exception as cost_err:
                    logger.error(f"Error in transcription cost tracking: {cost_err}")
                    import traceback
                    logger.debug(f"Cost tracking traceback: {traceback.format_exc()}")
                
                # Save result to temp file
                with open(temp_file, 'w') as f:
                    json.dump({
                        'transcription_result': result,
                        'duration': transcription_duration,
                        'completed_at': transcription_end_time
                    }, f)
            finally:
                # Stop progress tracking
                transcription_complete.set()
                progress_thread.join(timeout=1)
            
            # Update progress to 80% when transcription is complete
            self.update_job_status(job_id, 'processing', progress=80)
            
            if not result:
                self.update_job_status(job_id, 'failed', error="Transcription returned no result")
                if temp_file.exists():
                    temp_file.unlink()
                return False
            
            # Now that transcription is complete, save to database
            
            # Save transcript to database using standalone function
            try:
                # Get language code from result or use the provided one
                language_code = None
                if translate_to and "target_language" in result and "code" in result["target_language"]:
                    lang = result["target_language"]["code"]
                    language_code = f"{lang}-{lang.upper()}" if len(lang) == 2 else lang
                elif "detected_language" in result and "code" in result["detected_language"]:
                    lang = result["detected_language"]["code"]
                    language_code = f"{lang}-{lang.upper()}" if len(lang) == 2 else lang
                else:
                    language_code = language
                
                # Use the most appropriate text
                if translate_to and "translated_text" in result:
                    transcript_text = result["translated_text"]
                else:
                    transcript_text = result["text"]
                
                # Check for cancellation before database operations
                if self.check_job_cancellation(job_id):
                    logger.info(f"Job {job_id} cancelled before saving to database")
                    return False
                
                # Check for maximum text length issues
                if len(transcript_text) > 64000:  # MySQL TEXT type max is 65535 bytes
                    logger.warning(f"Transcript is too long ({len(transcript_text)} chars), truncating to 64000 chars")
                    transcript_text = transcript_text[:64000]
                
                # Use standalone save function
                transcript_id = save_transcript_to_db(space_id, transcript_text, language_code)
                
                if not transcript_id:
                    self.update_job_status(job_id, 'failed', 
                                          error="Failed to save transcript to database",
                                          result={"text_sample": transcript_text[:500] + "..."})
                    return False
                
                # Always run AI language detection on the transcript text for accuracy
                # This ensures we get the correct language even if Whisper misdetected it
                logger.info(f"Running AI language detection on transcript for space {space_id}")
                try:
                    # Use AI to detect language from a sample of the transcript
                    sample_text = transcript_text[:1000]  # Use first 1000 chars for detection
                    
                    # Check if AI is configured
                    ai_config_exists = False
                    ai_provider = None
                    
                    try:
                        with open("mainconfig.json", 'r') as f:
                            main_config = json.load(f)
                            
                        # Check if AI is configured
                        ai_config = main_config.get('ai', {})
                        if ai_config.get('provider'):
                            ai_config_exists = True
                            ai_provider = ai_config['provider']
                    except:
                        pass
                    
                    if ai_config_exists and ai_provider == 'openai':
                        from components.OpenAI import OpenAI
                        api_key = os.environ.get('OPENAI_API_KEY') or ai_config.get('openai', {}).get('api_key')
                        model = ai_config.get('openai', {}).get('model', 'gpt-4o-mini')
                        
                        if api_key:
                            logger.info(f"Using OpenAI for language detection with model: {model}")
                            ai = OpenAI(api_key, model=model)
                            
                            # Prepare prompt for language detection
                            prompt = f"""Analyze the following text and identify its language. Return ONLY the ISO 639-1 language code (2 letters).

Common language codes:
- en: English
- bn: Bengali/Bangla
- hi: Hindi
- ar: Arabic
- ur: Urdu
- es: Spanish
- fr: French
- de: German
- ja: Japanese
- ko: Korean
- zh: Chinese
- pt: Portuguese
- it: Italian
- ru: Russian
- tr: Turkish
- fa: Persian/Farsi

Text to analyze:
"{sample_text}"

Language code:"""

                            messages = [
                                {"role": "system", "content": "You are a language detection expert. Return only the 2-letter ISO 639-1 language code."},
                                {"role": "user", "content": prompt}
                            ]
                            
                            success, response = ai._make_request(messages, max_tokens=10, temperature=0.1)
                            
                            # Track AI cost for language detection
                            if success and isinstance(response, dict) and 'usage' in response:
                                try:
                                    ai_cost = AICost()
                                    usage = response['usage']
                                    input_tokens = usage.get('input_tokens', 0)
                                    output_tokens = usage.get('output_tokens', 0)
                                    
                                    # Track cost
                                    ai_cost.track_cost(
                                        space_id=space_id,
                                        action='language_detection',
                                        vendor='openai',
                                        model=ai.model,  # Use the model from AI component
                                        input_tokens=input_tokens,
                                        output_tokens=output_tokens
                                    )
                                    logger.info(f"Tracked AI cost for language detection: {input_tokens} input + {output_tokens} output tokens")
                                except Exception as cost_error:
                                    logger.warning(f"Failed to track AI cost for language detection: {cost_error}")
                            
                            if success:
                                # Extract content from the response dict
                                content = response.get('content', '') if isinstance(response, dict) else str(response)
                                detected_lang = content.strip().lower()
                                
                                # Validate the response is a proper language code
                                valid_codes = {
                                    'en', 'bn', 'hi', 'ar', 'ur', 'es', 'fr', 'de', 'ja', 'ko', 
                                    'zh', 'pt', 'it', 'ru', 'tr', 'fa', 'nl', 'sv', 'no', 'da'
                                }
                                
                                if detected_lang in valid_codes and detected_lang != language_code.split('-')[0]:
                                    logger.info(f"AI detected language: {detected_lang} (was: {language_code})")
                                    
                                    # Format language code with region
                                    new_language_code = f"{detected_lang}-{detected_lang.upper()}"
                                    
                                    # Update the language in database
                                    import mysql.connector
                                    connection = None
                                    cursor = None
                                    
                                    try:
                                        # Load database config
                                        with open("db_config.json", 'r') as f:
                                            config = json.load(f)
                                        
                                        db_config = config["mysql"].copy()
                                        if 'use_ssl' in db_config:
                                            del db_config['use_ssl']
                                        
                                        connection = mysql.connector.connect(**db_config)
                                        cursor = connection.cursor()
                                        
                                        # Update language for this transcript
                                        update_query = """
                                        UPDATE space_transcripts 
                                        SET language = %s, updated_at = NOW()
                                        WHERE id = %s
                                        """
                                        cursor.execute(update_query, (new_language_code, transcript_id))
                                        connection.commit()
                                        
                                        # Update language_code for the rest of the function
                                        language_code = new_language_code
                                        logger.info(f"Updated transcript language to {new_language_code} in database")
                                        
                                    except Exception as db_err:
                                        logger.error(f"Error updating language in database: {db_err}")
                                    finally:
                                        if cursor:
                                            try:
                                                cursor.close()
                                            except:
                                                pass
                                        if connection:
                                            try:
                                                connection.close()
                                            except:
                                                pass
                                
                                # Track AI cost for language detection
                                try:
                                    if user_id and user_id > 0:
                                        ai_cost = AICost()
                                        
                                        # Estimate tokens for language detection
                                        input_tokens = ai_cost.estimate_tokens(prompt, is_input=True)
                                        output_tokens = 5  # Just the language code
                                        
                                        # Track cost using unified AICost component
                                        success, message, cost = ai_cost.track_cost(
                                            space_id=space_id,
                                            action='language_detection',
                                            vendor='openai',
                                            model=model,
                                            input_tokens=input_tokens,
                                            output_tokens=output_tokens,
                                            user_id=user_id,
                                            cookie_id=None,
                                            deduct_credits=True
                                        )
                                        
                                        if success:
                                            logger.info(f"COST TRACKING: {message} - ${cost:.2f} for language detection")
                                        else:
                                            logger.warning(f"COST TRACKING: {message}")
                                            
                                except Exception as cost_err:
                                    logger.error(f"Error tracking language detection cost: {cost_err}")
                            else:
                                logger.warning(f"AI language detection failed: {response}")
                                
                    elif ai_config_exists and ai_provider == 'claude':
                        # Similar implementation for Claude if needed
                        logger.info("Claude language detection not implemented yet, using original language")
                    else:
                        logger.info("AI not configured for language detection, using original language")
                        
                except Exception as detect_err:
                    logger.error(f"Error in AI language detection: {detect_err}", exc_info=True)
                
                # Generate and save tags for English transcripts
                if language_code.startswith('en'):
                    generate_and_save_tags_with_ai(space_id, transcript_text)
                
                # Save original text as separate transcript if translation was done
                original_transcript_id = None
                if translate_to and "original_text" in result and "original_language" in result:
                    orig_lang = result["original_language"]
                    orig_lang_code = f"{orig_lang}-{orig_lang.upper()}" if len(orig_lang) == 2 else orig_lang
                    
                    original_text = result["original_text"]
                    if len(original_text) > 64000:
                        original_text = original_text[:64000]
                    
                    # Use standalone save function
                    original_transcript_id = save_transcript_to_db(space_id, original_text, orig_lang_code)
                
                # Get actual audio duration from Whisper result
                actual_duration = result.get("segments", [])
                if actual_duration:
                    # Get the end time of the last segment for actual duration
                    actual_duration_seconds = actual_duration[-1].get("end", 0)
                    actual_audio_minutes = actual_duration_seconds / 60
                else:
                    # Fallback to using the overall duration if available
                    actual_duration_seconds = result.get("duration", 0)
                    actual_audio_minutes = actual_duration_seconds / 60 if actual_duration_seconds else estimated_audio_minutes
                
                # Build result data
                result_data = {
                    "transcript_id": transcript_id,
                    "space_id": space_id,
                    "language": language_code,
                    "text_sample": transcript_text[:500] + "..." if len(transcript_text) > 500 else transcript_text,
                    "audio_duration_minutes": round(actual_audio_minutes, 1),
                    "audio_duration_seconds": round(actual_duration_seconds, 1)
                }
                
                if original_transcript_id:
                    result_data["original_transcript_id"] = original_transcript_id
                
                if "detected_language" in result:
                    result_data["detected_language"] = result["detected_language"]
                
                # Mark job as completed
                self.update_job_status(job_id, 'completed', progress=100, result=result_data)
                logger.info(f"Transcription job {job_id} completed successfully")
                
                # Send email notification
                try:
                    from components.NotificationHelper import NotificationHelper
                    
                    # Get user_id and space title from database
                    user_id = job.get('user_id')
                    space_title = None
                    
                    if not user_id:
                        # Try to get user_id from database if not in job
                        try:
                            with self.db_manager.get_connection() as connection:
                                cursor = connection.cursor(dictionary=True)
                                query = """
                                SELECT sdq.user_id, s.title
                                FROM space_download_scheduler sdq
                                LEFT JOIN spaces s ON sdq.space_id = s.space_id
                                WHERE sdq.space_id = %s
                                ORDER BY sdq.created_at DESC
                                LIMIT 1
                                """
                                cursor.execute(query, (space_id,))
                                result = cursor.fetchone()
                                if result:
                                    user_id = result['user_id']
                                    space_title = result['title']
                        except Exception as db_err:
                            logger.error(f"Error getting user info for notification: {db_err}")
                    
                    if user_id:
                        helper = NotificationHelper()
                        success = helper.send_job_completion_email(
                            user_id=user_id,
                            job_type='transcription',
                            space_id=space_id,
                            space_title=space_title,
                            additional_info={'language': language_code}
                        )
                        if success:
                            logger.info(f"Email notification sent to user {user_id}")
                        else:
                            logger.error("Failed to send email notification")
                    else:
                        logger.warning("Could not determine user_id for email notification")
                        
                except Exception as email_err:
                    logger.error(f"Error sending email notification: {email_err}")
                
                # Clean up temp file
                if temp_file.exists():
                    temp_file.unlink()
                    
                return True
                
            except Exception as db_err:
                logger.error(f"Error saving transcript to database: {db_err}")
                self.update_job_status(job_id, 'failed', 
                                     error=f"Error saving transcript: {str(db_err)}",
                                     result={"text_sample": result["text"][:500] + "..."})
                return False
            
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            self.update_job_status(job_id, 'failed', error=str(e))
            traceback.print_exc()
            return False
        finally:
            # Clean up temp file
            if 'temp_file' in locals() and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception as e:
                    logger.warning(f"Error deleting temp file: {e}")
            
            # Note: No database connections to clean up - all database operations
            # use standalone functions that manage their own connections
    
    def run(self):
        """Run the worker loop."""
        logger.info("Transcription worker starting")
        
        while self.running:
            try:
                # Get pending jobs
                pending_jobs = self.get_pending_jobs()
                
                if pending_jobs:
                    # Process the first pending job
                    job = pending_jobs[0]
                    job_id = job.get('job_id') or job.get('id')
                    space_id = job.get('space_id', 'unknown')
                    logger.info(f"Processing transcription job {job_id} for space {space_id}")
                    
                    # Check if job was cancelled before processing
                    if self.check_job_cancellation(job_id):
                        logger.info(f"Skipping cancelled job {job_id}")
                        continue
                    
                    # Process the job
                    self.process_job(job)
                
                # Wait before checking for more jobs
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                time.sleep(10)  # Wait longer if there was an error
        
        logger.info("Transcription worker stopped")

def main():
    parser = argparse.ArgumentParser(description='Background transcription worker for XSpace Downloader')
    parser.add_argument('--status-dir', type=str, default='./transcript_jobs',
                        help='Directory to store job status files')
    
    args = parser.parse_args()
    
    worker = TranscriptionWorker(status_dir=args.status_dir)
    worker.run()

if __name__ == '__main__':
    main()