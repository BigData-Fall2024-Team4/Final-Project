from .base import CanvasBaseAgent
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class AssignmentAgent(CanvasBaseAgent):
    """Agent for managing Canvas assignments"""

    async def create_assignment(self, course_id: str, name: str, description: str,
                              points: int, due_date: str, 
                              submission_types: List[str]) -> Dict[str, Any]:
        """Create a course assignment"""
        try:
            await self._ensure_session()
            payload = {
                'assignment': {
                    'name': name,
                    'description': description,
                    'points_possible': points,
                    'due_at': due_date,
                    'submission_types': submission_types
                }
            }
            
            async with self.session.post(
                f"{self.base_url}/api/v1/courses/{course_id}/assignments",
                headers=self.headers,
                json=payload
            ) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Error creating assignment: {str(e)}")
            return {"error": str(e)}

    async def get_assignments(self, course_id: str) -> Dict[str, Any]:
        """Get all assignments for a course"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.base_url}/api/v1/courses/{course_id}/assignments",
                headers=self.headers
            ) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Error getting assignments: {str(e)}")
            return {"error": str(e)}

    async def update_assignment(self, course_id: str, assignment_id: str, 
                              **updates) -> Dict[str, Any]:
        """Update an existing assignment"""
        try:
            await self._ensure_session()
            payload = {'assignment': updates}
            
            async with self.session.put(
                f"{self.base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}",
                headers=self.headers,
                json=payload
            ) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Error updating assignment: {str(e)}")
            return {"error": str(e)}