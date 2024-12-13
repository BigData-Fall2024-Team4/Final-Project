from typing import Dict, List
import logging
import requests
import numpy as np
from pinecone import Pinecone
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RAGQueryAgent:
    def __init__(self, api_key: str = None, api_url: str = None, 
                 pinecone_api_key: str = None, pinecone_index_name: str = None,
                 openai_api_key: str = None):
        """Initialize the RAG query agent"""
        try:
            self.pc = Pinecone(api_key=pinecone_api_key)
            self.index = self.pc.Index(pinecone_index_name)
            self.client = OpenAI(api_key=openai_api_key)
            self.api_key = api_key
            self.api_url = "https://integrate.api.nvidia.com/v1/embeddings"
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            logger.info("Successfully initialized RAG query agent")
        except Exception as e:
            logger.error(f"Failed to initialize RAG query agent: {str(e)}")
            raise

    def display_match_content(self, match, index: int):
        """Display detailed match content"""
        logger.info(f"\nMatch {index} Content Details:")
        logger.info("=" * 50)
        logger.info(f"ID: {match.id}")
        logger.info(f"Similarity Score: {match.score:.4f}")
        logger.info(f"Chunk Index: {match.metadata.get('chunk_index', 'N/A')}")
        logger.info(f"Source: {match.metadata.get('source', 'Unknown')}")
        logger.info("\nText Content:")
        logger.info("-" * 50)
        logger.info(match.metadata.get('text', 'No text available'))
        logger.info("=" * 50)

    def generate_embedding(self, text: str) -> Dict:
        """Generate embedding using NVIDIA API"""
        try:
            clean_text = text.strip()
            payload = {
                "input": clean_text,
                "model": "nvidia/embed-qa-4",
                "input_type": "query"
            }
            
            logger.info(f"Generating embedding for query: {clean_text[:100]}...")
            
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code != 200:
                logger.error(f"API error: {response.text}")
                return {"success": False, "error": f"API error: {response.text}"}
            
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                embedding = data['data'][0]['embedding']
                logger.info(f"Generated embedding with dimension: {len(embedding)}")
                return {"success": True, "embedding": embedding}
            
            return {"success": False, "error": "No embedding in response"}
            
        except Exception as e:
            logger.error(f"Embedding generation error: {str(e)}")
            return {"success": False, "error": str(e)}

    async def process_chunks(self, query: str, matches: List[dict]) -> str:
        """Process chunks with improved GPT-4 prompt"""
        try:
            # Format matches text
            chunks_text = "\n\n".join([
                f"Document Section {i} [Score: {match['score']:.4f}]:\n{match['text']}\n---"
                for i, match in enumerate(matches, 1)
            ])
            
            messages = [
                {"role": "system", "content": """You are a research assistant helping to analyze academic workshop information. 
                Focus on extracting key details about workshops, organizers, and relevant academic content."""},
                {"role": "user", "content": f"""
Query: {query}

Retrieved Document Sections:
{chunks_text}

Please provide a concise summary following this structure:

1. Workshop Details:
   - Name and type of workshop
   - Date and location
   - Parent conference/event

2. Key People:
   - Workshop chairs/organizers
   - Their affiliations

3. Additional Context:
   - Any other relevant details about the workshop
   - Related workshops or events mentioned

Note: Only include information explicitly present in the retrieved sections."""}
            ]
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.7
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"Error in LLM processing: {e}")
            return f"Error generating response: {str(e)}"

    async def process_query(self, message: str) -> Dict:
        """Process a RAG query end-to-end"""
        try:
            # Extract query
            query = message[message.find(']') + 1:].strip()
            if not query:
                return {"success": False, "response": "No query text found"}

            logger.info(f"\nProcessing Query: {query}")
            logger.info("=" * 50)

            # Generate embedding
            embed_result = self.generate_embedding(query)
            if not embed_result["success"]:
                return {"success": False, "response": f"Embedding error: {embed_result['error']}"}

            # Query Pinecone
            try:
                query_response = self.index.query(
                    vector=embed_result["embedding"],
                    top_k=5,
                    include_metadata=True
                )
            except Exception as e:
                logger.error(f"Pinecone query error: {str(e)}")
                return {"success": False, "response": f"Error querying document database: {str(e)}"}

            if not query_response.matches:
                return {"success": False, "response": "No matches found"}

            # Process matches
            matches_content = []
            logger.info("\nRetrieved Matches Analysis:")
            
            for i, match in enumerate(query_response.matches, 1):
                self.display_match_content(match, i)
                
                content = {
                    "score": match.score,
                    "text": match.metadata.get('text', 'No text available'),
                    "chunk_index": match.metadata.get('chunk_index', 'N/A'),
                    "source": match.metadata.get('source', 'Unknown')
                }
                matches_content.append(content)

            # Process with GPT-4
            gpt_response = await self.process_chunks(query, matches_content)

            return {
                "success": True,
                "response": gpt_response,
                "matches": matches_content
            }

        except Exception as e:
            logger.error(f"Error in query processing: {str(e)}")
            return {"success": False, "response": f"Error processing query: {str(e)}"}