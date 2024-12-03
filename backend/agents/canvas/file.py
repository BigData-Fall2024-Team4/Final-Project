from .base import CanvasBaseAgent
from typing import Dict, Any, BinaryIO
import logging

logger = logging.getLogger(__name__)

class FileAgent(CanvasBaseAgent):
    """Agent for managing Canvas files"""

    async def upload_file(self, course_id: str, file_name: str, 
                         file_data: bytes) -> Dict[str, Any]:
        """Upload a file to a course"""
        try:
            await self._ensure_session()
            # Get upload URL
            async with self.session.post(
                f"{self.base_url}/api/v1/courses/{course_id}/files",
                headers=self.headers,
                json={'name': file_name}
            ) as response:
                upload_data = await response.json()

            # Upload the file
            files = {'file': (file_name, file_data)}
            async with self.session.post(
                upload_data['upload_url'],
                data=upload_data['upload_params'],
                files=files
            ) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            return {"error": str(e)}

    async def get_files(self, course_id: str) -> Dict[str, Any]:
        """Get all files in a course"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.base_url}/api/v1/courses/{course_id}/files",
                headers=self.headers
            ) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Error getting files: {str(e)}")
            return {"error": str(e)}