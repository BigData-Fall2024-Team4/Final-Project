import aiohttp
import logging
from typing import Optional, Dict, Any, List, Tuple
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from duckduckgo_search import DDGS
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebSearchAgent:
    """Agent responsible for web searching and content extraction"""
    
    def __init__(self):
        self.session = None
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.conversation_history = []
        logger.info("Web Search Agent initialized")

    async def _ensure_session(self):
        """Ensure aiohttp session is created"""
        if self.session is None:
            self.session = aiohttp.ClientSession()

    def _extract_url_and_question(self, query: str, conversation_context: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
        """Extract URL and question from the query and context"""
        url_pattern = r'https?://[^\s<>"\']+'
        urls = re.findall(url_pattern, query)
        url = urls[0] if urls else None
        
        if not url and conversation_context:
            context_urls = re.findall(url_pattern, conversation_context)
            url = context_urls[-1] if context_urls else None
        
        question = re.sub(url_pattern, '', query).strip() if url else query
        question = question if question else None
        
        return url, question

    def _search_ddg(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Perform DuckDuckGo search with error handling"""
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                logger.info(f"Found {len(results)} results for query: {query}")
                return results
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {str(e)}")
            return []

    async def _fetch_url(self, url: str) -> Optional[str]:
        """Fetch content from URL with improved error handling"""
        try:
            await self._ensure_session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0'
            }
            async with self.session.get(url, headers=headers, timeout=20) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'text/html' in content_type:
                        html = await response.text()
                        return await self._clean_html(html)
                    else:
                        logger.warning(f"Unsupported content type for URL {url}: {content_type}")
                        return None
                else:
                    logger.warning(f"Failed to fetch URL {url}: Status {response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout while fetching URL {url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {str(e)}")
            return None

    async def _clean_html(self, html_content: str) -> str:
        """Clean HTML content and extract main text"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'meta', 'link']):
                element.decompose()
            
            # Try to find the main content
            main_content = None
            for selector in ['article', 'main', '.content', '.post-content', '.article-content', '#content', '.main-content']:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            text = main_content.get_text(separator=' ', strip=True) if main_content else soup.get_text(separator=' ', strip=True)
            
            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = ' '.join(lines)
            
            # Remove extra whitespace
            text = ' '.join(text.split())
            
            return text
        except Exception as e:
            logger.error(f"Error cleaning HTML: {str(e)}")
            return ""

    async def _search_and_summarize(self, query: str, conversation_context: Optional[str] = None) -> str:
        """Perform search and summarize results with better handling"""
        try:
            # Run DuckDuckGo search in thread pool
            search_results = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._search_ddg,
                query
            )

            if not search_results:
                return "I couldn't find any search results for your query."

            # Fetch content from URLs concurrently
            tasks = []
            for result in search_results:
                if url := result.get('link'):
                    task = asyncio.create_task(self._fetch_url(url))
                    tasks.append((result.get('title', ''), task))

            # Wait for all fetch tasks to complete
            contents = []
            for title, task in tasks:
                try:
                    if content := await task:
                        contents.append({
                            'title': title,
                            'content': content[:5000]  # Limit content length
                        })
                except Exception as e:
                    logger.error(f"Error processing search result: {str(e)}")

            if not contents:
                return "I found some web pages but couldn't access their content. Please try rephrasing your question or asking about something else."

            # Generate answer using combined content
            llm = ChatOpenAI()
            context_part = f"\nPrevious conversation context:\n{conversation_context}" if conversation_context else ""
            
            prompt = f"""
            {context_part}
            Based on the following search results, please provide a comprehensive answer to this question: "{query}"
            
            Search Results:
            {json.dumps(contents, indent=2)}
            
            Please provide a detailed and informative answer based on the available information.
            Include relevant facts and details from the sources.
            If the information is incomplete or uncertain, acknowledge that in your response.
            """
            
            response = await llm.apredict(prompt)
            
            # Add to conversation history
            self.conversation_history.append({
                "question": query,
                "answer": response,
                "sources": len(contents)
            })
            
            return response

        except Exception as e:
            logger.error(f"Error in search and summarize: {str(e)}")
            return "I encountered an error while searching for information. Please try again or rephrase your question."

    async def process(self, query: str, conversation_context: Optional[str] = None) -> str:
        """Main processing method for web search queries"""
        try:
            # Extract URL and question
            url, question = self._extract_url_and_question(query, conversation_context)
            
            # If no URL and no question, return error
            if not url and not question:
                return "I couldn't understand your query. Please provide a question or a URL to analyze."
            
            # If URL is provided, fetch its content
            content = None
            if url:
                content = await self._fetch_url(url)
                if not content:
                    logger.warning(f"Failed to fetch content from URL: {url}")
            
            # Process based on available information
            if not question and content:
                # No question but have content - summarize the content
                return self._get_answer_from_content(
                    content, 
                    "Summarize this content and highlight the key points.",
                    conversation_context
                )
            elif question and content:
                # Have both question and content - answer question using content
                return self._get_answer_from_content(
                    content,
                    question,
                    conversation_context
                )
            elif question:
                # Only have question - perform web search
                return await self._search_and_summarize(question, conversation_context)
            else:
                return "I couldn't process your request. Please try asking a question or providing a valid URL."

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return "I encountered an error while processing your request. Please try again."

    def _get_answer_from_content(self, content: str, question: str, conversation_context: Optional[str] = None) -> str:
        """Get answer from content with improved prompting"""
        try:
            llm = ChatOpenAI()
            
            context_prompt = ""
            if conversation_context:
                context_prompt = f"""
                Previous conversation context:
                {conversation_context}
                Please consider this context in your response.
                """
            
            prompt = f"""
            {context_prompt}
            
            Question: {question}
            
            Content to analyze:
            {content[:4000]}
            
            Instructions:
            1. Provide a clear and detailed answer based on the content
            2. Include specific information and facts from the content
            3. If the content doesn't fully answer the question, acknowledge what's missing
            4. If referencing the previous conversation, make that clear
            5. Keep the response focused and relevant to the question
            
            Please ensure your response is informative and well-structured.
            """
            
            response = llm.predict(prompt)
            self.conversation_history.append({
                "question": question,
                "answer": response
            })
            return response
            
        except Exception as e:
            logger.error(f"Error generating answer: {str(e)}")
            return "I encountered an error while generating the answer. Please try again."

    async def close(self):
        """Cleanup method"""
        if self.session:
            await self.session.close()
            self.session = None
        self.executor.shutdown(wait=True)