import re
import json
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

def preprocess_text(text: str) -> List[str]:
    """
    Preprocess raw text into a list of cleaned words/phrases.
    This function organizes raw text into a structured format.
    
    Args:
        text: Raw text input containing words/phrases
        
    Returns:
        List of cleaned and normalized words/phrases
    """
    # Log input text length
    logger.info(f"Preprocessing text of length: {len(text)}")
    
    # Remove extra whitespace
    text = text.strip()
    
    # First, normalize line endings and replace multiple spaces with single spaces
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\s+', ' ', text)
    
    # Split ONLY by periods (dots). Treat consecutive dots as one separator.
    items = re.split(r'\.+', text)
    
    # Log number of items after splitting
    logger.info(f"Split into {len(items)} raw items")
    
    # Clean up each item and further split if needed
    cleaned_items = []
    for item in items:
        item = item.strip()
        if not item:  # Skip empty items
            continue
            
        # Do not split by spaces anymore; keep the item as entered (phrase allowed)
        # Remove leading/trailing punctuation around the entire item
        item = re.sub(r'^[^\w]+|[^\w]+$', '', item)
        if item:
            cleaned_items.append(item)
    
    # Log the number of items found
    logger.info(f"Preprocessed {len(cleaned_items)} words from input text")
    
    # Log a sample of the words
    if cleaned_items:
        sample = cleaned_items[:5] if len(cleaned_items) > 5 else cleaned_items
        logger.info(f"Sample words: {', '.join(sample)}")
    
    return cleaned_items

def create_batches(items: List[str], batch_size: int) -> List[List[str]]:
    """
    Split a list of items into batches of specified size.
    
    Args:
        items: List of items to batch
        batch_size: Maximum number of items per batch
        
    Returns:
        List of batches, where each batch is a list of items
    """
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]

def prepare_batch_for_processing(batch: List[str]) -> str:
    """
    Convert a batch of words/phrases into a format suitable for AI processing.
    
    Args:
        batch: List of words/phrases
        
    Returns:
        JSON string representation of the batch
    """
    # Create a simple JSON structure with the words
    batch_data = {
        "words": batch
    }
    
    return json.dumps(batch_data, ensure_ascii=False)

class BatchProcessor:
    """
    Manages the preprocessing and batch processing of text input.
    """
    
    def __init__(self, raw_text: str, batch_size: int = 20):
        """
        Initialize the batch processor.
        
        Args:
            raw_text: Raw text input
            batch_size: Number of items per batch (default: 20)
        """
        self.raw_text = raw_text
        self.batch_size = batch_size
        self.processed_items = []
        self.batches = []
        self.results = []
        self.failed_batches = {}
        self.prompts = {}  # Store the full prompts sent to AI
        self.preprocessing_details = {
            "raw_text": raw_text,
            "processed_items": []
        }
        
    def preprocess(self):
        """
        Preprocess the raw text and create batches.
        
        Returns:
            Self (for method chaining)
        """
        self.processed_items = preprocess_text(self.raw_text)
        self.preprocessing_details["processed_items"] = self.processed_items
        self.batches = create_batches(self.processed_items, self.batch_size)
        return self
    
    def get_preprocessing_details(self) -> dict:
        """
        Get details about the preprocessing step.
        
        Returns:
            Dictionary with preprocessing details
        """
        return self.preprocessing_details
        
    def store_prompt(self, batch_index: int, prompt: str):
        """
        Store the full prompt sent to the AI for a specific batch.
        
        Args:
            batch_index: Batch index
            prompt: Full prompt text
        """
        self.prompts[batch_index] = prompt
    
    def get_prompt(self, batch_index: int) -> str:
        """
        Get the full prompt for a specific batch.
        
        Args:
            batch_index: Batch index
            
        Returns:
            Full prompt text or empty string if not found
        """
        return self.prompts.get(batch_index, "")
    
    def get_batch_count(self) -> int:
        """
        Get the number of batches.
        
        Returns:
            Number of batches
        """
        return len(self.batches)
    
    def get_batch(self, index: int) -> List[str]:
        """
        Get a specific batch by index.
        
        Args:
            index: Batch index
            
        Returns:
            List of items in the batch
        """
        if 0 <= index < len(self.batches):
            return self.batches[index]
        return []
    
    def get_batch_for_processing(self, index: int) -> str:
        """
        Get a specific batch formatted for AI processing.
        
        Args:
            index: Batch index
            
        Returns:
            JSON string representation of the batch
        """
        batch = self.get_batch(index)
        return prepare_batch_for_processing(batch)
    
    def mark_batch_as_failed(self, index: int, error: str):
        """
        Mark a batch as failed with the error message.
        
        Args:
            index: Batch index
            error: Error message
        """
        if index not in self.failed_batches:
            self.failed_batches[index] = {"attempts": 0, "error": error}
        
        self.failed_batches[index]["attempts"] += 1
        self.failed_batches[index]["error"] = error
    
    def add_batch_result(self, index: int, result: Dict[str, Any]):
        """
        Add result for a processed batch.
        
        Args:
            index: Batch index
            result: Processing result
        """
        if 0 <= index < len(self.batches):
            self.results.append(result)
            # Remove from failed batches if it was there
            if index in self.failed_batches:
                del self.failed_batches[index]
    
    def get_failed_batches(self) -> Dict[int, Dict]:
        """
        Get all failed batches.
        
        Returns:
            Dictionary of batch indices to failure information
        """
        return self.failed_batches
    
    def get_retryable_batches(self) -> List[int]:
        """
        Get indices of batches that can be retried (less than 3 attempts).
        
        Returns:
            List of batch indices
        """
        return [idx for idx, info in self.failed_batches.items() if info["attempts"] < 3]
    
    def get_permanently_failed_batches(self) -> List[int]:
        """
        Get indices of batches that have failed permanently (3 or more attempts).
        
        Returns:
            List of batch indices
        """
        return [idx for idx, info in self.failed_batches.items() if info["attempts"] >= 3]
    
    def get_all_results(self) -> List[Dict[str, Any]]:
        """
        Get all successful batch results.
        
        Returns:
            List of batch results
        """
        return self.results 

    def get_failed_details(self) -> Dict[int, Dict[str, Any]]:
        """
        Return a mapping of failed batch indices to their failure information
        (attempt count and latest error message).
        """
        return dict(self.failed_batches)