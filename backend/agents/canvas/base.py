import aiohttp
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class CanvasBaseAgent:
    """Base class for Canvas API interactions"""
    
    def __init__(self, canvas_api_key: str, canvas_base_url: str):
        self.api_key = canvas_api_key
        self.base_url = canvas_base_url.rstrip('/')
        self.session = None
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    async def _ensure_session(self):
        """Ensure aiohttp session is created"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def get_course_id(self, course_name: str) -> Optional[str]:
        """Get Canvas course ID from course name"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.base_url}/api/v1/courses",
                headers=self.headers
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