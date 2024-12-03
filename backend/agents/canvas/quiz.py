from .base import CanvasBaseAgent
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class QuizAgent(CanvasBaseAgent):
    """Agent for managing Canvas quizzes"""

    async def create_quiz(self, course_id: str, title: str, description: str,
                         quiz_type: str = 'assignment', 
                         time_limit: int = None) -> Dict[str, Any]:
        """Create a course quiz"""
        try:
            await self._ensure_session()
            payload = {
                'quiz': {
                    'title': title,
                    'description': description,
                    'quiz_type': quiz_type,
                    'time_limit': time_limit
                }
            }
            
            async with self.session.post(
                f"{self.base_url}/api/v1/courses/{course_id}/quizzes",
                headers=self.headers,
                json=payload
            ) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Error creating quiz: {str(e)}")
            return {"error": str(e)}

    async def add_question(self, course_id: str, quiz_id: str, 
                          question_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a question to a quiz"""
        try:
            await self._ensure_session()
            async with self.session.post(
                f"{self.base_url}/api/v1/courses/{course_id}/quizzes/{quiz_id}/questions",
                headers=self.headers,
                json={'question': question_data}
            ) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Error adding quiz question: {str(e)}")
            return {"error": str(e)}