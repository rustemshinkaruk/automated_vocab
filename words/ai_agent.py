import json
import os
from openai import OpenAI
import logging

# Set up logging
logger = logging.getLogger(__name__)

def get_openai_models():
    """Get available OpenAI models"""
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        models = client.models.list()
        # Filter for language models only
        model_names = [model.id for model in models.data if model.id.startswith(('gpt-', 'text-'))]
        return model_names
    except Exception as e:
        logger.error(f"Error fetching OpenAI models: {e}")
        # Return an error message
        return ["API call for models list failed"]

def process_text_with_ai(text, provider, model_name, language):
    """
    Process text with AI (supports multiple providers)
    
    Args:
        text (str): Text to process
        provider (str): AI provider name ('OpenAI', 'Gemini', etc.)
        model_name (str): AI model to use
        language (str): Language for processing
        
    Returns:
        dict: Processed data from AI
    """
    if not text:
        return {"error": "No text provided"}
    
    # Default prompt for French words
    
    prompt_template = """
    this prompt is currently not used. the good one defined in gemin_agent.py
    
    """
    
    # Format the prompt with the text
    prompt = prompt_template.format(language=language, text=text)
    
    # Log the parameters
    logger.info(f"Processing text with model: {model_name}, language: {language}")
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
        # Call the OpenAI API
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful linguistic assistant that analyzes text and extracts structured information."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=4000
        )
        
        # Get the response content
        content = response.choices[0].message.content
        
        # Try to parse the JSON from the response
        try:
            # Extract JSON from the response (it might be wrapped in backticks)
            json_content = _extract_json(content)
            result = json.loads(json_content)
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return {"error": "Failed to parse response from AI model", "raw_response": content}
            
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return {"error": f"API call failed: {str(e)}"}

def _extract_json(text):
    """Extract JSON from text that might contain markdown code blocks."""
    if "```json" in text:
        # Extract JSON from markdown code block
        parts = text.split("```json")
        json_part = parts[1].split("```")[0]
        return json_part.strip()
    elif "```" in text:
        # Extract from generic code block
        parts = text.split("```")
        if len(parts) >= 2:
            return parts[1].strip()
    
    # Return the original text if no code blocks found
    return text.strip() 