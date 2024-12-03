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
import time
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

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
        self.last_search_time = 0
        self.min_search_interval = 2  # Minimum seconds between searches
        self.last_successful_results = []
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

    def _enforce_rate_limit(self):
        """Enforce rate limiting between searches"""
        current_time = time.time()
        time_since_last = current_time - self.last_search_time
        if time_since_last < self.min_search_interval:
            time.sleep(self.min_search_interval - time_since_last)
        self.last_search_time = time.time()

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception)
    )
    def _search_ddg(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Perform DuckDuckGo search with retries and rate limiting"""
        try:
            self._enforce_rate_limit()
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                if not results:
                    # Try alternative search if no results
                    simplified_query = ' '.join(query.split()[:3])  # Use first 3 words
                    results = list(ddgs.text(simplified_query, max_results=max_results))
                
                logger.info(f"Found {len(results)} results for query: {query}")
                self.last_successful_results = results  # Cache successful results
                return results
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {str(e)}")
            if self.last_successful_results:
                logger.info("Using cached results due to search error")
                return self.last_successful_results
            raise

    async def _fetch_url(self, url: str, retries: int = 3) -> Optional[str]:
        """Fetch content from URL with retries and improved error handling"""
        for attempt in range(retries):
            try:
                await self._ensure_session()
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'DNT': '1',
                    'Connection': 'keep-alive'
                }
                timeout = aiohttp.ClientTimeout(total=20)
                async with self.session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status == 200:
                        content_type = response.headers.get('content-type', '').lower()
                        if 'text/html' in content_type:
                            html = await response.text()
                            return await self._clean_html(html)
                        else:
                            logger.warning(f"Unsupported content type for URL {url}: {content_type}")
                            return None
                    elif response.status == 429:  # Rate limit
                        wait_time = int(response.headers.get('Retry-After', 5))
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.warning(f"Failed to fetch URL {url}: Status {response.status}")
                        return None
            except asyncio.TimeoutError:
                logger.error(f"Timeout while fetching URL {url} (attempt {attempt + 1})")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
            except Exception as e:
                logger.error(f"Error fetching URL {url} (attempt {attempt + 1}): {str(e)}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
        return None

    async def _clean_html(self, html_content: str) -> str:
        """Clean HTML content and extract main text"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'meta', 'link', 'noscript']):
                element.decompose()
            
            # Try to find the main content
            main_content = None
            for selector in ['article', 'main', '.content', '.post-content', '.article-content', '#content', '.main-content']:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            text = main_content.get_text(separator=' ', strip=True) if main_content else soup.get_text(separator=' ', strip=True)
            
            # Clean up text
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = ' '.join(lines)
            text = ' '.join(text.split())
            text = re.sub(r'\s+', ' ', text)
            
            return text
        except Exception as e:
            logger.error(f"Error cleaning HTML: {str(e)}")
            return ""

    async def _search_and_summarize(self, query: str, conversation_context: Optional[str] = None) -> str:
        """Perform search and summarize results"""
        try:
            # Run DuckDuckGo search in thread pool
            search_results = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._search_ddg,
                query
            )

            if not search_results:
                return await self._get_llm_fallback_response(query, conversation_context)

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
                return await self._get_llm_fallback_response(query, conversation_context)

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
            return await self._get_llm_fallback_response(query, conversation_context)

    async def _get_llm_fallback_response(self, question: str, conversation_context: Optional[str] = None) -> str:
        """Generate a response using LLM when web search fails"""
        try:
            llm = ChatOpenAI()
            context_part = f"\nPrevious conversation context:\n{conversation_context}" if conversation_context else ""
            
            prompt = f"""
            {context_part}
            I need to provide information about: "{question}"
            Please provide a helpful response based on general knowledge.
            Be clear about any uncertainties and stick to widely known facts.
            """
            
            return await llm.apredict(prompt)
        except Exception as e:
            logger.error(f"Error in LLM fallback: {str(e)}")
            return "I'm unable to provide specific information at the moment. Please try again later."

    async def process(self, query: str, conversation_context: Optional[str] = None) -> str:
        """Main processing method with improved error handling"""
        try:
            # Extract URL and question
            url, question = self._extract_url_and_question(query, conversation_context)
            
            # If no URL and no question, try to extract meaningful query
            if not url and not question:
                cleaned_query = re.sub(r'\[.*?\]', '', query).strip()  # Remove square brackets
                if cleaned_query:
                    question = cleaned_query
                else:
                    return "I couldn't understand your query. Please provide a question or a URL to analyze."
            
            # Process based on available information
            if question:
                # Perform web search with fallback
                try:
                    result = await self._search_and_summarize(question, conversation_context)
                    if result and len(result) > 50:  # Check if result is substantial
                        return result
                except Exception as e:
                    logger.error(f"Error in web search: {str(e)}")
                    # Fallback to direct LLM response
                    return await self._get_llm_fallback_response(question, conversation_context)
            
            if url:
                content = await self._fetch_url(url)
                if content:
                    return await self._get_answer_from_content(content, question or "Summarize this content", conversation_context)
            
            return "I encountered some issues while processing your request. Please try rephrasing your question or providing a different URL."

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return "I encountered an error processing your request. Please try again with a simpler query."

    async def _get_answer_from_content(self, content: str, question: str, conversation_context: Optional[str] = None) -> str:
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
            
            response = await llm.apredict(prompt)
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