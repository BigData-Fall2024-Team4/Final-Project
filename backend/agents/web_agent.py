import aiohttp
import logging
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from duckduckgo_search import DDGS
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re
import json
import aiohttp
from typing import Optional, Dict, Any, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSearchAgent:
    """Agent responsible for web searching and content extraction"""
    
    def __init__(self):
        self.session = None
        self.executor = ThreadPoolExecutor(max_workers=3)
        logger.info("Web Search Agent initialized")

    async def _ensure_session(self):
        """Ensure aiohttp session is created"""
        if self.session is None:
            self.session = aiohttp.ClientSession()

    def _extract_url_and_question(self, query: str) -> tuple[Optional[str], Optional[str]]:
        """Extract URL and question from the query"""
        import re
        
        # URL pattern matching
        url_pattern = r'https?://[^\s<>"\']+'
        urls = re.findall(url_pattern, query)
        url = urls[0] if urls else None
        
        # Remove URL from query to get the question
        question = re.sub(url_pattern, '', query).strip() if url else query
        question = question if question else None
        
        return url, question

    async def _fetch_url(self, url: str) -> Optional[str]:
        """Fetch content from URL"""
        try:
            await self._ensure_session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            async with self.session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    return await self._clean_html(html)
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {str(e)}")
            return None

    async def _clean_html(self, html_content: str) -> str:
        """Clean HTML content and extract main text"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'meta', 'link']):
                element.decompose()
            
            # Get main content (prioritize article or main content areas)
            main_content = soup.find('article') or soup.find('main') or soup.find('div', class_='content')
            
            if main_content:
                text = main_content.get_text(separator=' ', strip=True)
            else:
                text = soup.get_text(separator=' ', strip=True)
            
            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = ' '.join(lines)
            
            return text
        except Exception as e:
            logger.error(f"Error cleaning HTML: {str(e)}")
            return ""

    def _get_answer_from_content(self, content: str, question: str) -> str:
        """Extract relevant answer from content based on the question"""
        try:
            llm = ChatOpenAI()
            prompt = f"""
            Based on the following content, please answer this question: "{question}"
            
            Content:
            {content[:4000]}  # Limiting content length for token constraints
            
            Please provide a clear and direct answer based only on the information from the content.
            If the information isn't available in the content, please state that clearly.
            """
            
            return llm.predict(prompt)
        except Exception as e:
            logger.error(f"Error generating answer: {str(e)}")
            return "I encountered an error while generating the answer."

    async def process(self, query: str) -> str:
        """Process web search query and return relevant information"""
        try:
            # Extract URL and question from query
            url, question = self._extract_url_and_question(query)
            
            if not url and not question:
                return "I couldn't find a URL or question in your query. Please provide a URL, a question, or both."
            
            # If URL is provided, fetch its content
            content = None
            if url:
                content = await self._fetch_url(url)
                if not content:
                    return f"I couldn't access the content from the URL: {url}"
            
            # If no question, provide a summary of the content
            if not question:
                return self._get_answer_from_content(content, "What is the main information in this content?")
            
            # If there's a question but no URL/content, perform web search
            if question and not content:
                logger.info(f"No URL provided, performing web search for: {question}")
                return await self._search_and_summarize(question)
            
            # If both content and question are available, answer the question
            return self._get_answer_from_content(content, question)

        except Exception as e:
            logger.error(f"Error processing web search: {str(e)}")
            return f"Error processing your request: {str(e)}"

    async def _search_and_summarize(self, query: str) -> str:
        """Perform search and summarize results when no URL is provided"""
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
            
            if not results:
                return "I couldn't find any relevant information about that topic."
            
            # Fetch content from search results
            contents = []
            for result in results:
                url = result.get('link')
                if url:
                    content = await self._fetch_url(url)
                    if content:
                        contents.append({
                            'title': result.get('title', ''),
                            'content': content[:3000]  # Limit content length
                        })
            
            if not contents:
                return "I found some results but couldn't access their content."
            
            # Generate answer using combined content
            llm = ChatOpenAI()
            prompt = f"""
            Based on the following search results, please answer this question: "{query}"
            
            Sources:
            {json.dumps(contents, indent=2)}
            
            Please provide a clear and direct answer based on the available information.
            If the information isn't available in the sources, please state that clearly.
            """
            
            return await llm.apredict(prompt)

        except Exception as e:
            logger.error(f"Error in search and summarize: {str(e)}")
            return f"I encountered an error while searching for information: {str(e)}"

    async def close(self):
        """Close the aiohttp session and executor"""
        if self.session:
            await self.session.close()
            self.session = None
        self.executor.shutdown(wait=True)