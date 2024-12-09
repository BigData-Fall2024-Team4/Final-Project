from typing import Dict, Any, Optional
import aiohttp
import logging
import re
from .base import CanvasBaseAgent
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

class PagesAgent(CanvasBaseAgent):
    """Agent for handling Canvas page operations"""
    
    def __init__(self, api_key: str, base_url: str):
        super().__init__(api_key, base_url)
        self.llm = ChatOpenAI()
        
    def _extract_link(self, message: str) -> Optional[str]:
        """Extract link from message if specified with 'link:' prefix"""
        try:
            if "link:" in message.lower():
                link_start = message.lower().index("link:") + 5
                link_end = message.find("\n", link_start)
                if link_end == -1:
                    link_end = len(message)
                link = message[link_start:link_end].strip()
                logger.info(f"Extracted link: {link}")
                return link
            return None
        except Exception as e:
            logger.error(f"Error extracting link: {str(e)}")
            return None

    async def _generate_title(self, content: str) -> str:
        """Generate a title for the page using LLM if not provided"""
        try:
            prompt = f"""
            Generate a brief, descriptive title (maximum 5 words) for the following content:
            {content[:500]}
            """
            title = await self.llm.apredict(prompt)
            return title.strip() or "New Page"
        except Exception as e:
            logger.error(f"Error generating title: {str(e)}")
            return "New Page"

    def _create_url_title(self, title: str) -> str:
        """Create a URL-safe version of the title"""
        # Remove special characters and convert spaces to hyphens
        url_title = re.sub(r'[^\w\s-]', '', title.lower())
        url_title = re.sub(r'[-\s]+', '-', url_title).strip('-')
        return url_title

    async def create_page(
    self,
    course_id: str,
    title: str,
    body: str,
    published: bool = True,
    editing_roles: str = "teachers",
    notify_of_update: bool = False
) -> Dict[str, Any]:
        """Create a new page in a Canvas course"""
        try:
            await self._ensure_session()
            
            # Validate and clean inputs
            if not title or not title.strip():
                title = "New Page"
            title = title.strip()
            
            # Create URL-safe version of title
            url_title = self._create_url_title(title)
            
            # Format URL for external links
            if body.startswith(('http://', 'https://')):
                body = f'<p><a href="{body}" target="_blank">{body}</a></p>'
            
            endpoint = f"{self.base_url}/api/v1/courses/{course_id}/pages/{url_title}"
            
            # Log request details
            logger.info(f"Creating page with:")
            logger.info(f"Title: {title}")
            logger.info(f"URL: {url_title}")
            logger.info(f"Course ID: {course_id}")
            logger.info(f"Endpoint: {endpoint}")
            
            # Format request data according to Canvas API specification
            data = {
                'wiki_page[title]': title,
                'wiki_page[body]': body.strip(),
                'wiki_page[published]': "true" if published else "false",
                'wiki_page[editing_roles]': editing_roles,
                'wiki_page[notify_of_update]': "true" if notify_of_update else "false",
                'wiki_page[front_page]': "false"
            }
            
            logger.info(f"Request data: {data}")
            
            async with self.session.put(  # Changed to PUT request
                endpoint,
                headers=self.headers,
                json=data
            ) as response:
                response_text = await response.text()
                logger.info(f"Canvas API Response Status: {response.status}")
                logger.info(f"Canvas API Response: {response_text}")
                
                if response.status in [200, 201]:
                    result = await response.json()
                    logger.info(f"Successfully created page '{title}' in course {course_id}")
                    return {
                        'success': True,
                        'page_id': result.get('page_id'),
                        'title': result.get('title'),
                        'url': result.get('html_url'),
                        'created_at': result.get('created_at')
                    }
                else:
                    error_msg = f"Failed to create page: {response_text}"
                    logger.error(error_msg)
                    return {
                        'success': False,
                        'message': error_msg
                    }
                    
        except Exception as e:
            error_msg = f"Error in create_page: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg
            }

    async def process_page_request(self, content: str, message: str) -> Dict[str, Any]:
        """Process a page creation request"""
        try:
            # Extract course name
            course_match = re.search(r'\[(.*?)\]', message)
            if not course_match:
                return {
                    'success': False,
                    'message': "Please specify a course name in square brackets, e.g. [Course Name]"
                }
                
            course_name = course_match.group(1)
            course_id = await self.get_course_id(course_name)
            
            if not course_id:
                return {
                    'success': False,
                    'message': f"Could not find course: {course_name}"
                }
                
            # Extract title
            title = None
            if "title:" in message.lower():
                title_match = re.search(r'title:\s*([^\n]+)', message, re.IGNORECASE)
                if title_match:
                    title = title_match.group(1).strip()
            
            # Check for link in message
            link = self._extract_link(message)
            if link:
                body = link
                if not title:
                    title = "External Resource"
            else:
                if "Text:" in message:
                    text_start = message.index("Text:") + 5
                    body = message[text_start:].strip()
                else:
                    body = content
                
                if not title:
                    title = await self._generate_title(body)
            
            logger.info(f"Processing page request for course: {course_name}")
            logger.info(f"Title: {title}")
            logger.info(f"Content type: {'link' if link else 'text'}")
            
            # Create the page
            result = await self.create_page(
                course_id=course_id,
                title=title,
                body=body,
                published=True
            )
            
            return {
                'success': result.get('success', False),
                'message': result.get('message', f"Successfully created page '{title}' in {course_name}"),
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