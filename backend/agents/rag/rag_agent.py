import logging
import re
from typing import Dict, Optional
import requests
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RAGQueryAgent:
    """Agent for handling RAG queries using NVIDIA embed-qa-4 model"""
    
    def __init__(self, api_key: str = None, api_url: str = None):
        """Initialize the RAG query agent with NVIDIA API credentials."""
        try:
            self.api_key = api_key
            # Override the API URL to use the correct integration endpoint
            self.api_url = "https://integrate.api.nvidia.com/v1"
            
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            logger.info("Successfully initialized RAG query agent with NVIDIA API")
        except Exception as e:
            logger.error(f"Failed to initialize RAG query agent: {str(e)}")
            raise

    def _print_embedding_details(self, embedding: np.ndarray):
        """Print embedding details in a formatted way"""
        print("\nEmbedding Details:")
        print("-" * 50)
        print(f"Dimensions: {len(embedding)}")
        print(f"First 10 dimensions: {embedding[:10]}")
        print(f"Vector norm: {np.linalg.norm(embedding)}")
        print("-" * 50)
            
    def generate_query_embedding(self, query: str) -> Dict[str, any]:
        """Generate embedding for a given query using NVIDIA's API."""
        try:
            # Use the OpenAI-compatible embeddings endpoint
            endpoint = f"{self.api_url}/embeddings"
            
            # Include input_type in the main payload
            payload = {
                "input": query,
                "model": "nvidia/embed-qa-4",
                "input_type": "query"  # Required parameter for NVIDIA's model
            }
            
            logger.info(f"Sending request to NVIDIA API endpoint: {endpoint}")
            logger.debug(f"Request payload: {payload}")
            
            # Make request to NVIDIA API
            response = requests.post(
                endpoint,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            # Log response for debugging
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response content: {response.text[:500]}")  # First 500 chars
            
            # Check for errors
            if response.status_code != 200:
                error_msg = f"API request failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
            
            # Extract embedding from response
            result = response.json()
            
            # Get embedding from response format
            if 'data' in result and len(result['data']) > 0 and 'embedding' in result['data'][0]:
                embedding = np.array(result['data'][0]['embedding'])
            else:
                raise Exception("No embedding found in API response")
            
            # Normalize the embedding
            normalized_embedding = embedding / np.linalg.norm(embedding)
            
            # Print embedding details
            self._print_embedding_details(normalized_embedding)
            
            return {
                "success": True,
                "embedding": normalized_embedding.tolist(),
                "dimensions": len(normalized_embedding),
                "norm": float(np.linalg.norm(normalized_embedding))
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = f"API request failed: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Error generating query embedding: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }

    async def process_query(self, message: str) -> Dict[str, any]:
        """Process a RAG query from user message."""
        try:
            # Extract PDF name and query
            pdf_match = re.search(r'pdf\[(.*?)\]', message)
            if not pdf_match:
                return {
                    "success": False,
                    "error": "PDF name not found in query. Please use format: query the pdf[PDF_NAME]",
                    "response": "Please specify a PDF name in brackets, e.g., query the pdf[ABC]"
                }
            
            pdf_name = pdf_match.group(1).strip()
            query_text = message[message.find(']') + 1:].strip()
            
            if not query_text:
                return {
                    "success": False,
                    "error": "No query text provided",
                    "response": "Please provide a query after the PDF name"
                }
            
            # Generate embedding
            embedding_result = self.generate_query_embedding(query_text)
            
            if not embedding_result["success"]:
                return {
                    "success": False,
                    "error": embedding_result.get("error", "Unknown error"),
                    "response": f"Error generating embedding: {embedding_result.get('error', 'Unknown error')}"
                }
                
            return {
                "success": True,
                "response": f"Generated embedding for query against PDF '{pdf_name}'\nQuery: {query_text}",
                "embedding": embedding_result["embedding"],
                "pdf_name": pdf_name,
                "query": query_text,
                "dimensions": embedding_result["dimensions"],
                "norm": embedding_result["norm"]
            }
            
        except Exception as e:
            logger.error(f"Error processing RAG query: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "response": f"Error processing query: {str(e)}"
            }

    async def close(self):
        """Cleanup method"""
        logger.info("RAG query agent closed")