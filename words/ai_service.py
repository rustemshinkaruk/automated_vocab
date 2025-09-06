import os
import json
import logging
import time
from django.core.cache import cache
import datetime
from typing import Dict, List, Any, Optional, Tuple
from .ai_agent import get_openai_models, process_text_with_ai
from .gemini_agent import get_gemini_models, process_text_with_gemini

# Import the prompt from gemini_agent.py
from .gemini_agent import process_text_with_gemini as gemini_processor

# Set up logging
logger = logging.getLogger(__name__)

# Available AI providers
AI_PROVIDERS = ['OpenAI', 'Gemini', 'Anthropic']

def get_models_for_provider(provider):
    """
    Get available models for the specified AI provider
    
    Args:
        provider (str): AI provider name ('OpenAI', 'Gemini', or 'Anthropic')
        
    Returns:
        list: Available model names
    """
    if provider == 'OpenAI':
        return get_openai_models()
    elif provider == 'Gemini':
        return get_gemini_models()
    elif provider == 'Anthropic':
        return ['claude-3-opus', 'claude-3-sonnet', 'claude-3-haiku']
    else:
        logger.error(f"Unknown AI provider: {provider}")
        return ["Unknown provider"]

def process_batch(batch_text: str, provider: str, model: str, language: str) -> Dict[str, Any]:
    """
    Process a batch of words with the specified AI provider.
    
    Args:
        batch_text: JSON string with batch data
        provider: AI provider name
        model: AI model name
        language: Language for processing
        
    Returns:
        Processing result
    """
    try:
        # Parse the batch text
        batch_data = json.loads(batch_text)
        batch_index = batch_data.get("batch_index", 0)
        words = batch_data.get("words", [])
        
        # Format words as comma-separated list
        formatted_words = ", ".join(words)
        
        # Log the batch
        logger.info(f"Processing batch with {len(words)} words using {provider} {model}")
        
        # Process with the appropriate provider
        if provider == 'OpenAI':
            result = process_text_with_ai(formatted_words, provider, model, language)
        elif provider == 'Gemini':
            # Use Gemini-specific processor so Gemini model IDs are valid
            result = process_text_with_gemini(formatted_words, model, language)
        elif provider == 'Anthropic':
            # Use Anthropic-specific processor
            result = process_with_anthropic(formatted_words, model, language)
        else:
            return {"error": f"Unsupported provider: {provider}"}
        
        # Add batch information to result without clobbering AI payload
        # Keep original AI output field "words" intact and store input words separately
        result["batch_index"] = batch_index
        result["input_words"] = words
        
        return result
    except json.JSONDecodeError as e:
        return {"error": f"Invalid batch data: {str(e)}"}
    except Exception as e:
        return {"error": f"Error processing batch: {str(e)}"}

def process_text(text: str, provider: str, model: str, language: str) -> Dict[str, Any]:
    """
    Process text with the specified AI provider and model.
    This is a wrapper around process_batch for backward compatibility.
    
    Args:
        text: Raw text to process
        provider: AI provider name
        model: AI model name
        language: Language for processing
        
    Returns:
        Dictionary with processing results
    """
    # Create a simple batch with the entire text
    batch_data = {"words": [text]}
    batch_text = json.dumps(batch_data, ensure_ascii=False)
    
    return process_batch(batch_text, provider, model, language)

def process_with_openai(text: str, model: str, language: str) -> Dict[str, Any]:
    """Process text with OpenAI API"""
    try:
        import openai
        
        # Check if API key is set
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            return {"error": "OpenAI API key not found. Please set the OPENAI_API_KEY environment variable."}
        
        client = openai.OpenAI(api_key=api_key)
        
        # Create the prompt
        system_prompt = f"""
        You are a language learning assistant specialized in {language}. 
        For each word or phrase provided, extract the following information:
        
        1. Noun form (if applicable)
        2. Verb form (if applicable)
        3. Adjective form (if applicable)
        4. Adverb form (if applicable)
        5. Synonym for each form (if applicable)
        6. Antonym for each form (if applicable)
        7. Frequency (common, uncommon, rare)
        8. Category (e.g., food, travel, emotions)
        9. Secondary category (if applicable)
        10. A brief explanation
        11. 1-2 example sentences
        
        Format your response as a JSON array of objects, where each object represents a word or phrase.
        
        Example format:
        ```json
        {
          "words": [
            {
              "original_phrase": "original phrase",
              "noun_form": "noun form",
              "verb_form": "verb form",
              "adjective_form": "adjective form",
              "adverb_form": "adverb form",
              "synonym_noun_form": "synonym for noun",
              "synonym_verb_form": "synonym for verb",
              "synonym_adjective_form": "synonym for adjective",
              "synonym_adverb_form": "synonym for adverb",
              "antonym_noun_form": "antonym for noun",
              "antonym_verb_form": "antonym for verb",
              "antonym_adjective_form": "antonym for adjective",
              "antonym_adverb_form": "antonym for adverb",
              "frequency": "common",
              "category": "primary category",
              "category_2": "secondary category",
              "explanation": "brief explanation",
              "examples": [
                "Example sentence 1",
                "Example sentence 2"
              ]
            }
          ]
        }
        ```
        
        If a field is not applicable, use null or omit it.
        """
        
        user_prompt = f"Please analyze the following {language} words or phrases:\n\n{text}"
        
        # Make the API call
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=4000
        )
        
        # Extract and parse the response
        result_text = response.choices[0].message.content
        
        # Extract JSON from the response
        json_start = result_text.find('{')
        json_end = result_text.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = result_text[json_start:json_end]
            result = json.loads(json_str)
            return result
        else:
            return {"error": "Failed to extract JSON from response", "raw_response": result_text}
    
    except Exception as e:
        logger.error(f"Error with OpenAI: {str(e)}")
        return {"error": f"Error with OpenAI: {str(e)}"}

def process_with_gemini(text: str, model: str, language: str) -> Dict[str, Any]:
    """Process text with Google Gemini API"""
    try:
        # Use the existing processor from gemini_agent.py
        return gemini_processor(text, model, language)
    
    except Exception as e:
        logger.error(f"Error with Gemini: {str(e)}")
        return {"error": f"Error with Gemini: {str(e)}"}

def process_with_anthropic(text: str, model: str, language: str) -> Dict[str, Any]:
    """Process text with Anthropic Claude API"""
    try:
        import anthropic
        
        # Check if API key is set
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return {"error": "Anthropic API key not found. Please set the ANTHROPIC_API_KEY environment variable."}
        
        client = anthropic.Anthropic(api_key=api_key)
        
        # Create the prompt
        system_prompt = f"""
        You are a language learning assistant specialized in {language}. 
        For each word or phrase provided, extract the following information:
        
        1. Noun form (if applicable)
        2. Verb form (if applicable)
        3. Adjective form (if applicable)
        4. Adverb form (if applicable)
        5. Synonym for each form (if applicable)
        6. Antonym for each form (if applicable)
        7. Frequency (common, uncommon, rare)
        8. Category (e.g., food, travel, emotions)
        9. Secondary category (if applicable)
        10. A brief explanation
        11. 1-2 example sentences
        
        Format your response as a JSON object with a "words" array, where each item represents a word or phrase.
        
        Example format:
        ```json
        {{
          "words": [
            {{
              "original_phrase": "original phrase",
              "noun_form": "noun form",
              "verb_form": "verb form",
              "adjective_form": "adjective form",
              "adverb_form": "adverb form",
              "synonym_noun_form": "synonym for noun",
              "synonym_verb_form": "synonym for verb",
              "synonym_adjective_form": "synonym for adjective",
              "synonym_adverb_form": "synonym for adverb",
              "antonym_noun_form": "antonym for noun",
              "antonym_verb_form": "antonym for verb",
              "antonym_adjective_form": "antonym for adjective",
              "antonym_adverb_form": "antonym for adverb",
              "frequency": "common",
              "category": "primary category",
              "category_2": "secondary category",
              "explanation": "brief explanation",
              "examples": [
                "Example sentence 1",
                "Example sentence 2"
              ]
            }}
          ]
        }}
        ```
        
        If a field is not applicable, use null or omit it.
        """
        
        user_prompt = f"Please analyze the following {language} words or phrases:\n\n{text}"
        
        # Make the API call
        response = client.messages.create(
            model=model,
            system=system_prompt,
            max_tokens=4000,
            temperature=0.2,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # Extract and parse the response
        result_text = response.content[0].text
        
        # Extract JSON from the response
        json_start = result_text.find('{')
        json_end = result_text.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = result_text[json_start:json_end]
            result = json.loads(json_str)
            return result
        else:
            return {"error": "Failed to extract JSON from response", "raw_response": result_text}
    
    except Exception as e:
        logger.error(f"Error with Anthropic: {str(e)}")
        return {"error": f"Error with Anthropic: {str(e)}"}

def process_batches(processor, provider: str, model: str, language: str, request=None) -> Tuple[bool, str]:
    """
    Process all batches sequentially.
    
    Args:
        processor: BatchProcessor instance
        provider: AI provider name
        model: AI model name
        language: Language for processing
        request: The HTTP request object (optional, for updating session)
        
    Returns:
        Tuple of (success_flag, message)
    """
    total_batches = processor.get_batch_count()
    if total_batches == 0:
        return False, "No batches to process"
    
    # Prepare stop control key if we have request
    stop_key = None
    if request is not None:
        try:
            if not request.session.session_key:
                request.session.save()
        except Exception:
            pass
        stop_key = f"processing_stop_{request.session.session_key}"
        # Clear any stale stop flag before starting a new run
        try:
            cache.delete(stop_key)
        except Exception:
            pass

    user_stopped = False

    # Process all batches sequentially
    for i in range(total_batches):
        # Check for stop request before starting next batch
        if stop_key and cache.get(stop_key):
            user_stopped = True
            if request and 'processing_info' in request.session:
                request.session['processing_info']['status'] = 'stopped'
                request.session.modified = True
                try:
                    request.session.save()
                except Exception:
                    pass
            break
        batch_text = processor.get_batch_for_processing(i)
        try:
            logger.info(f"Processing batch {i+1}/{total_batches}")
            
            # Track batch start time
            batch_start_time = datetime.datetime.now()
            
            # Update processing info in session if request is provided
            if request and 'processing_info' in request.session:
                request.session['processing_info'].update({
                    'current_batch': i+1,
                    'batch_start_time': str(batch_start_time)
                })
                request.session.modified = True
            
            # Parse the batch text to get the words
            batch_data = json.loads(batch_text)
            words = batch_data.get("words", [])
            formatted_words = ", ".join(words)  # Format as comma-separated list
            
            # Generate the full prompt based on provider
            full_prompt = ""
            if provider == 'OpenAI':
                system_prompt = create_openai_system_prompt(language)
                user_prompt = f"Please analyze the following {language} words or phrases:\n\n{formatted_words}"
                full_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
            elif provider == 'Gemini':
                full_prompt = create_gemini_prompt(language, formatted_words)
            elif provider == 'Anthropic':
                system_prompt = create_anthropic_system_prompt(language)
                user_prompt = f"Please analyze the following {language} words or phrases:\n\n{formatted_words}"
                full_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
            
            # Store the full prompt
            processor.store_prompt(i, full_prompt)
            
            # Process the batch
            result = process_batch(batch_text, provider, model, language)
            
            # Track batch end time
            batch_end_time = datetime.datetime.now()
            batch_duration = (batch_end_time - batch_start_time).total_seconds()
            
            if "error" in result:
                processor.mark_batch_as_failed(i, result["error"])
                logger.error(f"Batch {i+1} failed: {result['error']}")
                
                # Update processing info in session if request is provided
                if request and 'processing_info' in request.session:
                    batch_info = {
                        'batch_number': i+1,
                        'start_time': str(batch_start_time),
                        'end_time': str(batch_end_time),
                        'duration': batch_duration,
                        'status': 'failed',
                        'error': result["error"]
                    }
                    
                    request.session['processing_info']['batch_times'].append(batch_info)
                    request.session.modified = True
                    try:
                        request.session.save()
                    except Exception:
                        pass
            else:
                processor.add_batch_result(i, result)
                logger.info(f"Batch {i+1} processed successfully in {batch_duration:.2f} seconds")
                
                # Update processing info in session if request is provided
                if request and 'processing_info' in request.session:
                    batch_info = {
                        'batch_number': i+1,
                        'start_time': str(batch_start_time),
                        'end_time': str(batch_end_time),
                        'duration': batch_duration,
                        'status': 'success',
                        'words_count': len(words)
                    }
                    
                    request.session['processing_info']['completed_batches'] += 1
                    request.session['processing_info']['batch_times'].append(batch_info)
                    request.session.modified = True
                    try:
                        request.session.save()
                    except Exception:
                        pass

            # Check after finishing a batch whether a stop was requested
            if stop_key and cache.get(stop_key):
                user_stopped = True
                if request and 'processing_info' in request.session:
                    request.session['processing_info']['status'] = 'stopped'
                    request.session.modified = True
                    try:
                        request.session.save()
                    except Exception:
                        pass
                break
        except Exception as e:
            processor.mark_batch_as_failed(i, str(e))
            logger.error(f"Exception processing batch {i+1}: {str(e)}")
            
            # Update processing info in session if request is provided
            if request and 'processing_info' in request.session:
                batch_end_time = datetime.datetime.now()
                batch_info = {
                    'batch_number': i+1,
                    'start_time': str(batch_start_time) if 'batch_start_time' in locals() else None,
                    'end_time': str(batch_end_time),
                    'status': 'error',
                    'error': str(e)
                }
                
                if 'batch_start_time' in locals():
                    batch_info['duration'] = (batch_end_time - batch_start_time).total_seconds()
                
                request.session['processing_info']['batch_times'].append(batch_info)
                request.session.modified = True
                try:
                    request.session.save()
                except Exception:
                    pass
    
    # Retry failed batches (up to 2 more attempts)
    for attempt in range(2):
        if user_stopped:
            break
        retryable_batches = processor.get_retryable_batches()
        if not retryable_batches:
            break
            
        logger.info(f"Retry attempt {attempt+1} for {len(retryable_batches)} failed batches")
        
        for batch_idx in retryable_batches:
            batch_text = processor.get_batch_for_processing(batch_idx)
            try:
                if stop_key and cache.get(stop_key):
                    user_stopped = True
                    if request and 'processing_info' in request.session:
                        request.session['processing_info']['status'] = 'stopped'
                        request.session.modified = True
                        try:
                            request.session.save()
                        except Exception:
                            pass
                    break
                logger.info(f"Retrying batch {batch_idx+1}/{total_batches}")
                
                # Track batch start time for retry
                retry_start_time = datetime.datetime.now()
                
                # Update processing info in session if request is provided
                if request and 'processing_info' in request.session:
                    request.session['processing_info'].update({
                        'current_batch': f"{batch_idx+1} (retry {attempt+1})",
                        'batch_start_time': str(retry_start_time)
                    })
                    request.session.modified = True
                    try:
                        request.session.save()
                    except Exception:
                        pass
                
                # Add a small delay before retrying
                time.sleep(1)
                # Check just before retry call as well
                if stop_key and cache.get(stop_key):
                    user_stopped = True
                    if request and 'processing_info' in request.session:
                        request.session['processing_info']['status'] = 'stopped'
                        request.session.modified = True
                        try:
                            request.session.save()
                        except Exception:
                            pass
                    break
                result = process_batch(batch_text, provider, model, language)
                
                # Track batch end time for retry
                retry_end_time = datetime.datetime.now()
                retry_duration = (retry_end_time - retry_start_time).total_seconds()
                
                if "error" in result:
                    processor.mark_batch_as_failed(batch_idx, result["error"])
                    logger.error(f"Batch {batch_idx+1} failed again: {result['error']}")
                    
                    # Update processing info in session if request is provided
                    if request and 'processing_info' in request.session:
                        retry_info = {
                            'batch_number': f"{batch_idx+1} (retry {attempt+1})",
                            'start_time': str(retry_start_time),
                            'end_time': str(retry_end_time),
                            'duration': retry_duration,
                            'status': 'failed',
                            'error': result["error"]
                        }
                        
                        request.session['processing_info']['batch_times'].append(retry_info)
                        request.session.modified = True
                        try:
                            request.session.save()
                        except Exception:
                            pass
                else:
                    processor.add_batch_result(batch_idx, result)
                    logger.info(f"Batch {batch_idx+1} processed successfully on retry in {retry_duration:.2f} seconds")
                    
                    # Update processing info in session if request is provided
                    if request and 'processing_info' in request.session:
                        retry_info = {
                            'batch_number': f"{batch_idx+1} (retry {attempt+1})",
                            'start_time': str(retry_start_time),
                            'end_time': str(retry_end_time),
                            'duration': retry_duration,
                            'status': 'success'
                        }
                        
                        request.session['processing_info']['completed_batches'] += 1
                        request.session['processing_info']['batch_times'].append(retry_info)
                        request.session.modified = True
                        try:
                            request.session.save()
                        except Exception:
                            pass
            
            except Exception as e:
                processor.mark_batch_as_failed(batch_idx, str(e))
                logger.error(f"Exception retrying batch {batch_idx+1}: {str(e)}")
                
                # Update processing info in session if request is provided
                if request and 'processing_info' in request.session:
                    retry_end_time = datetime.datetime.now()
                    retry_info = {
                        'batch_number': f"{batch_idx+1} (retry {attempt+1})",
                        'start_time': str(retry_start_time) if 'retry_start_time' in locals() else None,
                        'end_time': str(retry_end_time),
                        'status': 'error',
                        'error': str(e)
                    }
                    
                    if 'retry_start_time' in locals():
                        retry_info['duration'] = (retry_end_time - retry_start_time).total_seconds()
                    
                    request.session['processing_info']['batch_times'].append(retry_info)
                    request.session.modified = True
                    try:
                        request.session.save()
                    except Exception:
                        pass
    
    # Check for permanently failed batches
    permanently_failed = processor.get_permanently_failed_batches()
    
    # Generate summary message
    success_count = len(processor.get_all_results())
    failed_count = len(permanently_failed)
    
    if user_stopped:
        message = f"Stopped by user. Processed {success_count} out of {total_batches} batches before stop."
        return success_count > 0, message
    if failed_count > 0:
        message = f"Processed {success_count} out of {total_batches} batches successfully. {failed_count} batches failed after 3 attempts."
        return success_count > 0, message
    else:
        message = f"All {total_batches} batches processed successfully."
        return True, message

def create_openai_system_prompt(language: str) -> str:
    """Create system prompt for OpenAI"""
    return f"""
    You are a language learning assistant specialized in {language}. 
    For each word or phrase provided, extract the following information:
    
    1. Noun form (if applicable)
    2. Verb form (if applicable)
    3. Adjective form (if applicable)
    4. Adverb form (if applicable)
    5. Synonym for each form (if applicable)
    6. Antonym for each form (if applicable)
    7. Frequency (common, uncommon, rare)
    8. Category (e.g., food, travel, emotions)
    9. Secondary category (if applicable)
    10. A brief explanation
    11. 1-2 example sentences
    
    Format your response as a JSON array of objects, where each object represents a word or phrase.
    
    Example format:
    ```json
    {{
      "words": [
        {{
          "original_phrase": "original phrase",
          "noun_form": "noun form",
          "verb_form": "verb form",
          "adjective_form": "adjective form",
          "adverb_form": "adverb form",
          "synonym_noun_form": "synonym for noun",
          "synonym_verb_form": "synonym for verb",
          "synonym_adjective_form": "synonym for adjective",
          "synonym_adverb_form": "synonym for adverb",
          "antonym_noun_form": "antonym for noun",
          "antonym_verb_form": "antonym for verb",
          "antonym_adjective_form": "antonym for adjective",
          "antonym_adverb_form": "antonym for adverb",
          "frequency": "common",
          "category": "primary category",
          "category_2": "secondary category",
          "explanation": "brief explanation",
          "examples": [
            "Example sentence 1",
            "Example sentence 2"
          ]
        }}
      ]
    }}
    ```
    
    If a field is not applicable, use null or omit it.
    """

def create_gemini_prompt(language: str, formatted_words: str) -> str:
    """Create prompt for Gemini using the existing prompt from gemini_agent.py"""
    # Extract the prompt template from gemini_agent's process_text_with_gemini function
    # Replace the dynamic parts with our parameters
    prompt = f"""
    this prompt is currently not used. the good one defined in gemin_agent.py
    """
    
    return prompt

def create_anthropic_system_prompt(language: str) -> str:
    """Create system prompt for Anthropic"""
    return f"""
    You are a language learning assistant specialized in {language}. 
    For each word or phrase provided, extract the following information:
    
    1. Noun form (if applicable)
    2. Verb form (if applicable)
    3. Adjective form (if applicable)
    4. Adverb form (if applicable)
    5. Synonym for each form (if applicable)
    6. Antonym for each form (if applicable)
    7. Frequency (common, uncommon, rare)
    8. Category (e.g., food, travel, emotions)
    9. Secondary category (if applicable)
    10. A brief explanation
    11. 1-2 example sentences
    
    Format your response as a JSON object with a "words" array, where each item represents a word or phrase.
    
    Example format:
    ```json
    {{
      "words": [
        {{
          "original_phrase": "original phrase",
          "noun_form": "noun form",
          "verb_form": "verb form",
          "adjective_form": "adjective form",
          "adverb_form": "adverb form",
          "synonym_noun_form": "synonym for noun",
          "synonym_verb_form": "synonym for verb",
          "synonym_adjective_form": "synonym for adjective",
          "synonym_adverb_form": "synonym for adverb",
          "antonym_noun_form": "antonym for noun",
          "antonym_verb_form": "antonym for verb",
          "antonym_adjective_form": "antonym for adjective",
          "antonym_adverb_form": "antonym for adverb",
          "frequency": "common",
          "category": "primary category",
          "category_2": "secondary category",
          "explanation": "brief explanation",
          "examples": [
            "Example sentence 1",
            "Example sentence 2"
          ]
        }}
      ]
    }}
    ```
    
    If a field is not applicable, use null or omit it.
    """ 