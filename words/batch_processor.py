import json
import logging
from typing import Dict, List, Any, Optional

from .preprocessing import preprocess_text
from .constants import DEFAULT_BATCH_SIZE

logger = logging.getLogger(__name__)

class BatchProcessor:
    """
    Handles batch processing of text input.
    
    This class is responsible for:
    1. Preprocessing text into individual words/phrases
    2. Splitting them into batches
    3. Tracking processing status
    4. Collecting results
    """
    
    def __init__(self, text: str, batch_size: int = DEFAULT_BATCH_SIZE):
        """
        Initialize the batch processor.
        
        Args:
            text: Raw text input
            batch_size: Number of words per batch
        """
        self.raw_text = text
        self.batch_size = batch_size
        self.words = []
        self.batches = []
        self.results = []
        self.failed_batches = {}
        self.prompts = {}
        
        # Log initialization
        logger.info(f"Initialized BatchProcessor with batch size: {batch_size}")
    
    def preprocess(self) -> 'BatchProcessor':
        """
        Preprocess the raw text and split into batches.
        Returns self for method chaining.
        """
        # Preprocess text into individual words/phrases
        self.words = preprocess_text(self.raw_text)
        
        # Log the number of words found
        logger.info(f"Preprocessed {len(self.words)} words from input text")
        
        # Split into batches
        self._create_batches()
        
        return self
    
    def _create_batches(self) -> None:
        """
        Split words into batches of the specified size.
        """
        self.batches = []
        
        # Check if we have any words to process
        if not self.words:
            logger.warning("No words to process after preprocessing")
            return
        
        # Log the number of words and batch size
        logger.info(f"Creating batches for {len(self.words)} words with batch size {self.batch_size}")
        
        # Split words into batches
        for i in range(0, len(self.words), self.batch_size):
            batch = self.words[i:i + self.batch_size]
            self.batches.append(batch)
        
        # Log batch creation
        logger.info(f"Created {len(self.batches)} batches with batch size {self.batch_size}")
        
        # Print all batches for debugging
        for i, batch in enumerate(self.batches):
            logger.info(f"Batch {i+1}/{len(self.batches)}: {len(batch)} words - {', '.join(batch[:5])}{'...' if len(batch) > 5 else ''}")
    
    def get_batch_count(self) -> int:
        """
        Get the total number of batches.
        """
        return len(self.batches)
    
    def get_batch(self, batch_idx: int) -> List[str]:
        """
        Get the words in a specific batch.
        
        Args:
            batch_idx: Index of the batch to retrieve
            
        Returns:
            List of words in the batch
        """
        if 0 <= batch_idx < len(self.batches):
            return self.batches[batch_idx]
        return []
    
    def get_batch_for_processing(self, batch_idx: int) -> str:
        """
        Get a batch formatted for AI processing.
        
        Args:
            batch_idx: Index of the batch to retrieve
            
        Returns:
            JSON string with batch data
        """
        if 0 <= batch_idx < len(self.batches):
            batch_data = {
                "batch_index": batch_idx,
                "words": self.batches[batch_idx]
            }
            return json.dumps(batch_data)
        return json.dumps({"batch_index": batch_idx, "words": []})
    
    def mark_batch_as_failed(self, batch_idx: int, error_msg: str) -> None:
        """
        Mark a batch as failed with an error message.
        
        Args:
            batch_idx: Index of the failed batch
            error_msg: Error message describing the failure
        """
        self.failed_batches[batch_idx] = {
            "attempts": self.failed_batches.get(batch_idx, {}).get("attempts", 0) + 1,
            "error": error_msg
        }
    
    def add_batch_result(self, batch_idx: int, result: Dict[str, Any]) -> None:
        """
        Add a successful batch result.
        
        Args:
            batch_idx: Index of the batch
            result: Processing result for the batch
        """
        # Add batch index to the result
        result["batch_index"] = batch_idx
        
        # Add the words that were in this batch
        if 0 <= batch_idx < len(self.batches):
            result["words"] = self.batches[batch_idx]
        
        self.results.append(result)
        
        # Remove from failed batches if it was there
        if batch_idx in self.failed_batches:
            del self.failed_batches[batch_idx]
    
    def store_prompt(self, batch_idx: int, prompt: str) -> None:
        """
        Store the prompt used for a batch.
        
        Args:
            batch_idx: Index of the batch
            prompt: The prompt used for processing
        """
        self.prompts[batch_idx] = prompt
    
    def get_prompt(self, batch_idx: int) -> Optional[str]:
        """
        Get the prompt used for a batch.
        
        Args:
            batch_idx: Index of the batch
            
        Returns:
            The prompt if available, None otherwise
        """
        return self.prompts.get(batch_idx)
    
    def get_failed_batches(self) -> List[int]:
        """
        Get indices of all failed batches.
        
        Returns:
            List of batch indices that failed
        """
        return list(self.failed_batches.keys())
    
    def get_retryable_batches(self) -> List[int]:
        """
        Get indices of batches that can be retried (failed fewer than 3 times).
        
        Returns:
            List of batch indices that can be retried
        """
        return [
            batch_idx for batch_idx, info in self.failed_batches.items()
            if info.get("attempts", 0) < 3
        ]
    
    def get_permanently_failed_batches(self) -> List[int]:
        """
        Get indices of batches that have permanently failed (3 or more attempts).
        
        Returns:
            List of batch indices that have permanently failed
        """
        return [
            batch_idx for batch_idx, info in self.failed_batches.items()
            if info.get("attempts", 0) >= 3
        ]
    
    def get_all_results(self) -> List[Dict[str, Any]]:
        """
        Get all successful batch results.
        
        Returns:
            List of successful batch results
        """
        return self.results

    def get_failed_details(self) -> Dict[int, Dict[str, Any]]:
        """
        Return detailed information for failed batches including attempts and error messages.

        Returns:
            Mapping from batch index to failure info.
        """
        return dict(self.failed_batches)
    
    def get_preprocessing_details(self) -> Dict[str, Any]:
        """
        Get details about the preprocessing.
        
        Returns:
            Dictionary with preprocessing details
        """
        # Get all batches with their words
        batch_details = []
        for i, batch in enumerate(self.batches):
            batch_details.append({
                "batch_index": i,
                "batch_number": i + 1,
                "word_count": len(batch),
                "words": batch
            })
            
        return {
            "original_text_length": len(self.raw_text),
            "words_count": len(self.words),
            "batch_count": len(self.batches),
            "batch_size": self.batch_size,
            "first_few_words": self.words[:10] if self.words else [],
            "all_words": self.words,
            "batches": batch_details
        } 