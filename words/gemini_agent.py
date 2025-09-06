import json
import os
import google.generativeai as genai
import logging

# Set up logging
logger = logging.getLogger(__name__)

def get_gemini_models():
    """Get available Gemini models"""
    try:
        # Configure the Gemini API
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        
        # List models that can generate content
        models = genai.list_models()
        
        # Filter for Gemini models only
        model_names = [model.name for model in models if "gemini" in model.name.lower()]
        
        # Return the model names
        return model_names
    except Exception as e:
        logger.error(f"Error fetching Gemini models: {e}")
        # Return an error message
        return ["API call for Gemini models failed"]

def process_text_with_gemini(text, model_name, language):
    """
    Process text with Google's Gemini API
    
    Args:
        text (str): Text to process
        model_name (str): Gemini model to use
        language (str): Language to process
        
    Returns:
        dict: Processed data from Gemini
    """
    if not text:
        return {"error": "No text provided"}
    
    # Configure the Gemini API
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    
    # Create the prompt, branching for Japanese to use the README-defined prompt (with 4 extra columns)
    if str(language).strip().lower() == "japanese":
        prompt = f"""
        Here is a list of {language} words. These words are separated by a dot. There are phrases that have commas inside of them and they should be treated as a whole phrase.
        
        Words: {text}
        
        For each word in the list, do the following:
        1) If it's a single word (not a phrase):
            - Check if the word has several derivational forms. For example, in french the word 'aimer' has several derivational forms: the noun 'amour', the adjective 'aimable', the present participle 'aimant', etc."
            - These words are all part of the same lexical family.
            - A single root can yield multiple words through derivation, each with a different grammatical function.
            - If the word has several derivational forms, find its noun form, verb form, adjective form, and adverb form.
            - return them in the infinitve form. 
            - Also generate example sentences for each derivational form that you found (create 4 sentences if possible, one for each word form). Provide the sentence examples only if you found a derivational word form, otherwise leave the examples field empty.
        2) If it is a phrase:
            - breakdown the phrase into individual words.
            - For each word that you identified in the phrase, perform the same steps as for a single word described above.
            - if it is an idiomatic expression then treat it as a single word and don't break it down into individual words.
        
        
        For original_phrase field in the JSON object:
        - check if the word correctly spelled. If it is not, write the correct form of the word and put the incorrect one in the parenthesis next to it.
        - If it's a phrase, use the entire phrase. also correctly spell the words in the phrase and put the incorrect ones in the parenthesis next to it.
        - Note that a phrase will have a separate entry for each unique word in it, but they willl all have the same original_phrase
        
        For the Frequnecy field in the JSON object:
        - assign a one of the following values : (essential, very common, common, uncommon, rare, very rare)
        - this will indicate the frequency of the word in the language.
        
        For the category field in the JSON object:
        - Assign a relevant semantic category to the word based on its meaning and typical usage.
        - there will be 1 category per word id (even if the word has the verb,noun,adjective,adverb forms, you should assign the same category to all the forms) 
        - The category should be intuitive and descriptive (e.g., household items, emotions, natural elements, professions, actions, tools, etc.), keep it simple and intuitive. avoid any categories with a slash bar like , just use general phrases or terms
        - Use only one concise category name per word. 
        For the category_2 field in the JSON object:
        - Assign a second category to the word based on its meaning and typical usage.
        - this category should be more specific than the  category field.
        - don't mention several cattegories for one word. it should be general and intuitive.  
        - if there is no second category, store null in the field.
        
        also provide synonyms and antonyms for each word form.
        - if there are no synonyms or antonyms, store null in the fields.
        
        For the explanation field, provide a short explanation of the word form.
        - pick only 1 word form to explain (the one that was provided in the input)
        - the explanation should be in language of the word.
        
        
        
        Respond ONLY with the JSON object, no additional text.
        Return the results as a JSON object with the following structure: (Follow the structure exactly)
        {{
            "words": [
                {{
                    "noun_form": "string or null",
                    "verb_form": "string or null",
                    "adjective_form": "string or null",
                    "adverb_form": "string or null",
                    "examples": ["example sentence 1", "example sentence 2", "example sentence 3", "example sentence 4"],
                    "original_phrase": "string",
                    "frequency": "string",
                    "category": "string",
                    "category_2": "string",
                    "synonym_noun_form": "string or null",
                    "synonym_verb_form": "string or null",
                    "synonym_adjective_form": "string or null",
                    "synonym_adverb_form": "string or null",
                    "antonym_noun_form": "string or null",
                    "antonym_verb_form": "string or null",
                    "antonym_adjective_form": "string or null",
                    "antonym_adverb_form": "string or null",
                    "explanation": "string",
                    "kanji_form": "string or null",
                    "kana_reading": "string",
                    "romaji": "string or null",  
                    "furigana": "string or null"
                }}
            ]
        }}
        
        
        """
    else:
        prompt = f"""
        Here is a list of {language} words. These words are separated by a dot. There are phrases that have commas inside of them and they should be treated as a whole phrase.
        
        Words: {text}
        
        For each word in the list, do the following:
        1) If it's a single word (not a phrase):
            - Check if the word has several derivational forms. For example, in french the word 'aimer' has several derivational forms: the noun 'amour', the adjective 'aimable', the present participle 'aimant', etc.
            - These words are all part of the same lexical family.
            - A single root can yield multiple words through derivation, each with a different grammatical function.
            - If the word has several derivational forms, find its noun form, verb form, adjective form, and adverb form.
            - return them in the infinitve form. 
            - Also generate example sentences for each derivational form that you found (create 4 sentences if possible, one for each word form). Provide the sentence examples only if you found a derivational word form, otherwise leave the examples field empty.
        2) If it is a phrase:
            - breakdown the phrase into individual words.
            - For each word that you identified in the phrase, perform the same steps as for a single word described above.
            - if it is an idiomatic expression then treat it as a single word and don't break it down into individual words.
        3) if the word is feminie or masculine, you can add the neccesary particle to the word to indicate the gender. you can also add (f) or (m) to the word to indicate the gender.  
            
        
        For original_phrase field in the JSON object:
        - check if the word correctly spelled. If it is not, write the correct form of the word and put the incorrect one in the parenthesis next to it.
        - If it's a phrase, use the entire phrase. also correctly spell the words in the phrase and put the incorrect ones in the parenthesis next to it.
        - Note that a phrase will have a separate entry for each unique word in it, but they willl all have the same original_phrase
        
        For the Frequnecy field in the JSON object:
        - assign a one of the following values : (essential, very common, common, uncommon, rare, very rare)
        - this will indicate the frequency of the word in the language.
        
        For the category field in the JSON object:
        - Assign a relevant semantic category to the word based on its meaning and typical usage.
        - there will be 1 category per word id (even if the word has the verb,noun,adjective,adverb forms, you should assign the same category to all the forms) 
        - The category should be intuitive and descriptive (e.g., household items, emotions, natural elements, professions, actions, tools, etc.), keep it simple and intuitive. avoid any categories with a slash bar like , just use general phrases or terms
        - Use only one concise category name per word. 
        For the category_2 field in the JSON object:
        - Assign a second category to the word based on its meaning and typical usage.
        - this category should be more specific than the  category field.
        - don't mention several cattegories for one word. it should be general and intuitive.  
        - if there is no second category, store null in the field.
        
        also provide synonyms and antonyms for each word form.
        - if there are no synonyms or antonyms, store null in the fields.
        
        For the explanation field, provide a short explanation of the word form.
        - pick only 1 word form to explain (the one that was provided in the input)
        - the explanation should be in language of the word.
        
        
        
        Respond ONLY with the JSON object, no additional text.
        Return the results as a JSON object with the following structure: (Follow the structure exactly)
        {{
            "words": [
                {{
                    "noun_form": "string or null",
                    "verb_form": "string or null",
                    "adjective_form": "string or null",
                    "adverb_form": "string or null",
                    "examples": ["example sentence 1", "example sentence 2", "example sentence 3", "example sentence 4"],
                    "original_phrase": "string",
                    "frequency": "string",
                    "category": "string",
                    "category_2": "string",
                    "synonym_noun_form": "string or null",
                    "synonym_verb_form": "string or null",
                    "synonym_adjective_form": "string or null",
                    "synonym_adverb_form": "string or null",
                    "antonym_noun_form": "string or null",
                    "antonym_verb_form": "string or null",
                    "antonym_adjective_form": "string or null",
                    "antonym_adverb_form": "string or null",
                    "explanation": "string"
                }}
            ]
        }}
        
        
        """
    
    # Log the parameters
    logger.info(f"Processing text with Gemini model: {model_name}, language: {language}")
    
    try:
        # Normalize model id (strip leading namespace like "models/")
        normalized_model = model_name.split('/')[-1] if model_name else model_name
        # Initialize Gemini model
        model = genai.GenerativeModel(normalized_model)
        
        # Generate content with safety/formatting constraints to enforce JSON
        response = model.generate_content(
            [
                {"role": "user", "parts": prompt},
            ]
        )
        
        # Get the response text
        content = response.text
        
        # Try to parse the JSON from the response
        try:
            # Extract JSON from the response (it might be wrapped in backticks)
            json_content = _extract_json(content)
            result = json.loads(json_content)
            # Ensure top-level has "words" key as list
            if isinstance(result, dict) and "words" in result and isinstance(result["words"], list):
                return result
            else:
                return {"error": "Model returned unexpected structure", "raw_response": content}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Gemini: {e}")
            return {"error": "Failed to parse response from Gemini model", "raw_response": content}
            
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        return {"error": f"Gemini API call failed: {str(e)}"}

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