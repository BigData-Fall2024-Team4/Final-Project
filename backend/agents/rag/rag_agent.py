import logging
import re
from typing import Dict, Optional
import requests
import numpy as np
from pinecone import Pinecone

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RAGQueryAgent:
    """Agent for handling RAG queries using NVIDIA embed-qa-4 model"""
    
    def __init__(self, api_key: str = None, api_url: str = None, 
                 pinecone_api_key: str = None, pinecone_index_name: str = None):
        """Initialize the RAG query agent with NVIDIA API and Pinecone credentials."""
        try:
            self.api_key = api_key
            self.api_url = "https://integrate.api.nvidia.com/v1"
            
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }

            # Initialize Pinecone with new method
            self.pc = Pinecone(api_key=pinecone_api_key)
            self.index = self.pc.Index(pinecone_index_name)
            
            logger.info("Successfully initialized RAG query agent")
        except Exception as e:
            logger.error(f"Failed to initialize RAG query agent: {str(e)}")
            raise

    def _print_embeddings_comparison(self, query_embedding: np.ndarray, similar_vectors: list):
        """Print query embedding and similar vectors details"""
        print("\nQuery Embedding Details:")
        print("-" * 50)
        print(f"Dimensions: {len(query_embedding)}")
        print(f"First 10 dimensions: {query_embedding[:10]}")
        print(f"Norm: {np.linalg.norm(query_embedding)}")
        
        print("\nTop 5 Similar Embeddings:")
        print("-" * 50)
        for i, match in enumerate(similar_vectors, 1):
            print(f"\nMatch {i}:")
            print(f"Score (Similarity): {match['score']:.4f}")
            print(f"PDF Source: {match['metadata']['source_id']}")
            if 'values' in match:
                vector = np.array(match['values'])
                print(f"First 10 dimensions: {vector[:10]}")
                print(f"Norm: {np.linalg.norm(vector)}")
            print("-" * 30)

    def generate_query_embedding(self, query: str) -> Dict[str, any]:
        """Generate embedding for a given query using NVIDIA's API."""
        try:
            endpoint = f"{self.api_url}/embeddings"
            
            payload = {
                "input": query,
                "model": "nvidia/embed-qa-4",
                "input_type": "query"
            }
            
            logger.info(f"Sending request to NVIDIA API endpoint: {endpoint}")
            
            response = requests.post(
                endpoint,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = f"API request failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            result = response.json()
            
            if 'data' in result and len(result['data']) > 0 and 'embedding' in result['data'][0]:
                embedding = np.array(result['data'][0]['embedding'])
                normalized_embedding = embedding / np.linalg.norm(embedding)
                return {
                    "success": True,
                    "embedding": normalized_embedding.tolist()
                }
            else:
                raise Exception("No embedding found in API response")
            
        except Exception as e:
            error_msg = f"Error generating query embedding: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    async def process_query(self, message: str) -> Dict[str, any]:
        """Process a RAG query from user message and find similar embeddings."""
        try:
            # Extract PDF name and query
            pdf_match = re.search(r'pdf\[(.*?)\]', message)
            if not pdf_match:
                return {
                    "success": False,
                    "error": "PDF name not found in query. Please use format: query the pdf[PDF_NAME]"
                }
            
            pdf_name = pdf_match.group(1).strip()
            query_text = message[message.find(']') + 1:].strip()
            
            if not query_text:
                return {
                    "success": False,
                    "error": "No query text provided"
                }
            
            # Generate embedding for query
            embedding_result = self.generate_query_embedding(query_text)
            if not embedding_result["success"]:
                return embedding_result
            
            # Query Pinecone for similar vectors
            query_response = self.index.query(
                vector=embedding_result["embedding"],
                top_k=5,
                include_values=True,
                include_metadata=True,
                filter={
                    "source_id": pdf_name
                }
            )
            
            # Print the comparison
            self._print_embeddings_comparison(
                np.array(embedding_result["embedding"]),
                query_response.matches
            )
            
            return {
                "success": True,
                "response": f"Found similar embeddings for query in PDF '{pdf_name}'",
                "query_embedding": embedding_result["embedding"],
                "similar_embeddings": [
                    {
                        "score": match.score,
                        "metadata": match.metadata,
                        "values": match.values if hasattr(match, 'values') else None
                    }
                    for match in query_response.matches
                ]
            }
            
        except Exception as e:
            logger.error(f"Error processing RAG query: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def close(self):
        """Cleanup method"""
        logger.info("RAG query agent closed")