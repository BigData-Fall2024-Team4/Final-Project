from .base import CanvasBaseAgent
from .announcement import AnnouncementAgent
from .assignment import AssignmentAgent
from .quiz import QuizAgent
from .file import FileAgent
from typing import Dict, Any, Optional, List
import logging
import aiohttp

logger = logging.getLogger(__name__)

class CanvasPostAgent:
    """Main agent for Canvas operations"""
    
    def __init__(self, canvas_api_key: str, canvas_base_url: str):
        self.api_key = canvas_api_key
        self.base_url = canvas_base_url.rstrip('/')
        self.session = None
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # Initialize sub-agents
        self.announcement_agent = AnnouncementAgent(self.api_key, self.base_url)
        self.assignment_agent = AssignmentAgent(self.api_key, self.base_url)
        self.quiz_agent = QuizAgent(self.api_key, self.base_url)
        self.file_agent = FileAgent(self.api_key, self.base_url)

    async def _ensure_session(self):
        """Ensure aiohttp session is created"""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
    async def process(self, content: str, message: str) -> Dict[str, Any]:
        """Process Canvas operations based on message content"""
        try:
            await self._ensure_session()
            
            # Extract course name and operation type
            if '[' not in message or ']' not in message:
                return {
                    "success": False,
                    "message": "Please specify a course name in square brackets, e.g. [Course Name]"
                }

            course_name = message[message.index('[')+1:message.index(']')]
            course_id = await self.get_course_id(course_name)

            if not course_id:
                return {
                    "success": False,
                    "message": f"Could not find course: {course_name}"
                }

            # Get title from message or use default
            title = self._extract_title(message)
            if not title:
                # Try to get it from the first line of content
                first_line = content.split('\n')[0].strip()
                if first_line and len(first_line) <= 100:  # Reasonable title length
                    title = first_line
                else:
                    title = "Generated Content"

            # Log the operation details
            logger.info(f"Processing {course_name} with title: {title}")

            # Determine content type and process accordingly
            result = None
            try:
                if "quiz" in message.lower():
                    logger.info(f"Creating quiz in course {course_name}")
                    result = await self.quiz_agent.create_quiz(
                        course_id, 
                        title,
                        content
                    )
                elif "assignment" in message.lower():
                    logger.info(f"Creating assignment in course {course_name}")
                    result = await self.assignment_agent.create_assignment(
                        course_id,
                        title,
                        content,
                        100,  # default points
                        None,  # no due date
                        ["online_text_entry"]
                    )
                else:
                    logger.info(f"Creating announcement in course {course_name}")
                    result = await self.announcement_agent.create_announcement(
                        course_id,
                        title,
                        content
                    )

                if isinstance(result, dict) and "error" in result:
                    logger.error(f"Error from sub-agent: {result['error']}")
                    return {
                        "success": False,
                        "message": str(result["error"])
                    }

                return {
                    "success": True,
                    "message": f"Successfully posted to {course_name}",
                    "details": result
                }

            except Exception as e:
                logger.error(f"Error in sub-agent operation: {str(e)}")
                return {
                    "success": False,
                    "message": f"Error in content creation: {str(e)}"
                }

        except Exception as e:
            logger.error(f"Error processing Canvas post: {str(e)}")
            return {
                "success": False,
                "message": f"Error processing request: {str(e)}"
            }

    def _extract_title(self, message: str) -> Optional[str]:
        """Extract title from message if specified with 'title:' prefix"""
        try:
            if "title:" in message.lower():
                title_start = message.lower().index("title:") + 6
                title_end = message.find("\n", title_start)
                if title_end == -1:
                    title_end = len(message)
                return message[title_start:title_end].strip()
            return None
        except Exception as e:
            logger.error(f"Error extracting title: {str(e)}")
            return None

    async def list_courses(self) -> List[Dict[str, Any]]:
        """Get list of all available courses"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.base_url}/api/v1/courses",
                headers=self.headers,
                params={
                    'enrollment_type': 'teacher',  # Only courses where user is teacher
                    'state[]': ['available', 'completed', 'created'],
                    'include[]': ['term', 'total_students']
                }
            ) as response:
                if response.status == 200:
                    courses = await response.json()
                    courses_list = [{
                        'id': course.get('id'),
                        'name': course.get('name'),
                        'code': course.get('course_code'),
                        'term': course.get('term', {}).get('name'),
                        'students': course.get('total_students', 0)
                    } for course in courses]
                    logger.info(f"Found {len(courses_list)} courses")
                    return courses_list
                    
                logger.error(f"Error listing courses: Status {response.status}")
                return []
        except Exception as e:
            logger.error(f"Error listing courses: {str(e)}")
            return []

    async def get_course_id(self, course_name: str) -> Optional[str]:
        """Get Canvas course ID from course name"""
        try:
            courses = await self.list_courses()
            for course in courses:
                if course_name.lower() in course['name'].lower():
                    logger.info(f"Found course ID {course['id']} for {course_name}")
                    return str(course['id'])
            logger.warning(f"No course found matching name: {course_name}")
            return None
        except Exception as e:
            logger.error(f"Error getting course ID: {str(e)}")
            return None

    async def close(self):
        """Close the session and all sub-agent sessions"""
        try:
            if self.session:
                await self.session.close()
                self.session = None
            
            # Close sub-agents' sessions
            await self.announcement_agent.close()
            await self.assignment_agent.close()
            await self.quiz_agent.close()
            await self.file_agent.close()
            logger.info("All sessions closed successfully")
        except Exception as e:
            logger.error(f"Error closing sessions: {str(e)}")