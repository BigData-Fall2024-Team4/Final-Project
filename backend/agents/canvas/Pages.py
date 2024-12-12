from typing import Dict, Any, Optional, Tuple
import aiohttp
import logging
import re
from .base import CanvasBaseAgent
from langchain_openai import ChatOpenAI
import html

logger = logging.getLogger(__name__)

class PagesAgent(CanvasBaseAgent):
    """Agent for handling Canvas page operations with LLM processing"""
    
    def __init__(self, api_key: str, base_url: str):
        super().__init__(api_key, base_url)
        self.llm = ChatOpenAI()

    async def _extract_content_with_llm(self, message: str) -> Dict[str, Any]:
        """
        Use LLM to extract title, text content, and determine content type
        """
        extraction_prompt = f"""Extract the following information from this message and remove any quotes from the text content:

        From this message: {message}

        1. If there's a title (after 'title:'), extract it
        2. If there's text content (after 'Text:'), extract ONLY the content itself, removing any quotes
        3. If there's a link (after 'link:'), extract it
        4. Extract the course name (text in square brackets)

        Return a clean JSON with these fields:
        {{
            "title": "extracted title or empty string",
            "text_content": "extracted text without quotes or empty string",
            "link": "extracted link or empty string",
            "course": "extracted course name without brackets or empty string",
            "content_type": "text" or "link"
        }}

        For example, if the input has 'Text:"Hello World"', the text_content should just be 'Hello World'
        """

        try:
            extracted_raw = await self.llm.apredict(extraction_prompt)
            extracted = eval(extracted_raw)
            
            # Additional cleanup for text content
            if extracted.get('text_content'):
                # Remove any remaining quotes
                extracted['text_content'] = extracted['text_content'].strip('"\'')
            
            logger.info(f"LLM extracted content: {extracted}")
            return extracted
        except Exception as e:
            logger.error(f"Error extracting content with LLM: {str(e)}")
            # Fallback to basic extraction
            return {
                "title": "",
                "text_content": "",
                "link": "",
                "course": "",
                "content_type": "text"
            }

    async def _format_content_with_llm(self, content: str, content_type: str) -> str:
        """
        Use LLM to format content into appropriate HTML
        """
        format_prompt = f"""Format this content into clean HTML for a Canvas page.
        Use appropriate semantic HTML elements (p, ul, ol, etc.).
        Add structure while preserving the content's meaning.

        Content Type: {content_type}
        Content: {content}

        Return only the formatted HTML without any explanation."""

        try:
            formatted_content = await self.llm.apredict(format_prompt)
            # Ensure there's at least a paragraph wrapper
            if not formatted_content.strip().startswith('<'):
                formatted_content = f"<p>{formatted_content}</p>"
            logger.info(f"LLM formatted content: {formatted_content}")
            return formatted_content
        except Exception as e:
            logger.error(f"Error formatting with LLM: {str(e)}")
            # Fallback to basic formatting
            return f"<p>{html.escape(content)}</p>"

    async def create_page(
        self,
        course_id: str,
        title: str,
        body: str,
        content_type: str = None,
        published: bool = True,
        editing_roles: str = "teachers"
    ) -> Dict[str, Any]:
        """Create a new page in a Canvas course"""
        try:
            await self._ensure_session()
            
            if not title or not title.strip():
                return {
                    'success': False,
                    'message': "Title cannot be blank"
                }
            
            endpoint = f"{self.base_url}/api/v1/courses/{course_id}/pages"
            
            logger.info(f"Creating page in course {course_id}")
            logger.info(f"Title: {title}")
            logger.info(f"Content Type: {content_type}")
            
            page_data = {
                "wiki_page": {
                    "title": title.strip(),
                    "body": body,
                    "editing_roles": editing_roles,
                    "published": published,
                    "notify_of_update": False
                }
            }
            
            logger.info(f"Request data: {page_data}")
            
            async with self.session.post(
                endpoint,
                headers=self.headers,
                json=page_data
            ) as response:
                response_text = await response.text()
                logger.info(f"Create page response status: {response.status}")
                logger.info(f"Create page response: {response_text}")
                
                if response.status not in [200, 201]:
                    return {
                        'success': False,
                        'message': f"Failed to create page: {response_text}"
                    }
                
                result = await response.json()
                return {
                    'success': True,
                    'page_id': result.get('page_id'),
                    'title': result.get('title'),
                    'url': result.get('html_url'),
                    'created_at': result.get('created_at'),
                    'published': result.get('published', False)
                }
                    
        except Exception as e:
            error_msg = f"Error in create_page: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg
            }

    async def process_page_request(self, content: str, message: str) -> Dict[str, Any]:
        """Process a page creation request using LLM for extraction and formatting"""
        try:
            # Use LLM to extract content and metadata
            extracted = await self._extract_content_with_llm(message)
            
            if not extracted.get('course'):
                return {
                    'success': False,
                    'message': "Please specify a course name in square brackets, e.g. [Course Name]"
                }
                
            course_name = extracted['course']
            course_id = await self.get_course_id(course_name)
            
            if not course_id:
                return {
                    'success': False,
                    'message': f"Could not find course: {course_name}"
                }
            
            # Use extracted content or fallbacks
            title = extracted.get('title') or "New Page"
            content_to_format = extracted.get('text_content') or extracted.get('link') or content
            content_type = extracted.get('content_type', 'text')
            
            # Use LLM to format the content
            formatted_content = await self._format_content_with_llm(content_to_format, content_type)
            
            logger.info(f"Processing page request:")
            logger.info(f"Course: {course_name}")
            logger.info(f"Title: {title}")
            logger.info(f"Content Type: {content_type}")
            logger.info(f"Formatted Content: {formatted_content}")
            
            # Create the page
            result = await self.create_page(
                course_id=course_id,
                title=title,
                body=formatted_content,
                content_type=content_type,
                published=True
            )
            
            if result.get('success'):
                message = f"Successfully created page '{title}' in {course_name}"
                if result.get('url'):
                    message += f"\nURL: {result['url']}"
            else:
                message = result.get('message', 'Unknown error occurred')
            
            return {
                'success': result.get('success', False),
                'message': message,
                'details': result
            }
                
        except Exception as e:
            error_msg = f"Error processing page request: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg
            }

    async def get_course_id(self, course_name: str) -> Optional[str]:
        """Get Canvas course ID from course name"""
        try:
            endpoint = f"{self.base_url}/api/v1/courses"
            params = {
                'enrollment_type': 'teacher',
                'state[]': ['available', 'completed', 'created']
            }
            
            async with self.session.get(
                endpoint,
                headers=self.headers,
                params=params
            ) as response:
                if response.status == 200:
                    courses = await response.json()
                    for course in courses:
                        if course_name.lower() in course['name'].lower():
                            return str(course['id'])
                return None
                
        except Exception as e:
            logger.error(f"Error getting course ID: {str(e)}")
            return None