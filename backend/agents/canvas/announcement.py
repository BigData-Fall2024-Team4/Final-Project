from .base import CanvasBaseAgent
from typing import Dict, Any, Tuple
import logging
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

class AnnouncementAgent(CanvasBaseAgent):
    """Agent for managing Canvas announcements"""

    async def generate_title(self, content: str) -> str:
        """Generate a title based on the content"""
        try:
            llm = ChatOpenAI()
            prompt = f"""
            Please create a short, descriptive title (maximum 5-7 words) for this content:
            
            {content[:500]}  # Using first 500 characters for context
            
            The title should:
            1. Be concise and informative
            2. Reflect the main topic
            3. Use title case
            4. Not exceed 7 words
            
            Return only the title, nothing else.
            """
            
            title = await llm.apredict(prompt)
            return title.strip()
        except Exception as e:
            logger.error(f"Error generating title: {str(e)}")
            return "Generated Content"  # Fallback title

    async def create_announcement(self, course_id: str, title: str, message: str, is_published: bool = True) -> Dict[str, Any]:
        """Create a course announcement"""
        try:
            await self._ensure_session()
            
            # If title is default, generate a new one
            if title == "Generated Content":
                title = await self.generate_title(message)
            
            # Format the message with HTML paragraph tags
            message_html = f'<p>{message}</p>'
            
            payload = {
                'title': title,
                'message': message_html,
                'is_announcement': True,
                'published': is_published,
                'allow_rating': True,  # Enable likes
                'specific_sections': 'all',  # Post to all sections
                'delayed_post_at': None,  # Post immediately
                'require_initial_post': False
            }
            
            async with self.session.post(
                f"{self.base_url}/api/v1/courses/{course_id}/discussion_topics",
                headers=self.headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to create announcement. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Failed to create announcement: {error_text}"}
                return await response.json()
        except Exception as e:
            logger.error(f"Error creating announcement: {str(e)}")
            return {"error": str(e)}

    async def get_announcements(self, course_id: str) -> Dict[str, Any]:
        """Get all announcements for a course"""
        try:
            await self._ensure_session()
            params = {
                'only_announcements': True
            }
            async with self.session.get(
                f"{self.base_url}/api/v1/courses/{course_id}/discussion_topics",
                headers=self.headers,
                params=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to get announcements. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Failed to get announcements: {error_text}"}
                return await response.json()
        except Exception as e:
            logger.error(f"Error getting announcements: {str(e)}")
            return {"error": str(e)}

    async def update_announcement(self, course_id: str, announcement_id: str, 
                                title: str = None, message: str = None) -> Dict[str, Any]:
        """Update an existing announcement"""
        try:
            await self._ensure_session()
            payload = {}
            if title:
                payload['title'] = title
            if message:
                payload['message'] = f'<p>{message}</p>'
                
            async with self.session.put(
                f"{self.base_url}/api/v1/courses/{course_id}/discussion_topics/{announcement_id}",
                headers=self.headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to update announcement. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Failed to update announcement: {error_text}"}
                return await response.json()
        except Exception as e:
            logger.error(f"Error updating announcement: {str(e)}")
            return {"error": str(e)}