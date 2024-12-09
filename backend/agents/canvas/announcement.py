from .base import CanvasBaseAgent
from typing import Dict, Any, Tuple
import logging
from langchain_openai import ChatOpenAI
import aiohttp

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

    async def create_announcement(self, course_id: str, title: str, message: str, 
                                is_published: bool = True, file_content: bytes = None,
                                file_name: str = None) -> Dict[str, Any]:
        """Create a course announcement with optional file attachment"""
        try:
            await self._ensure_session()
            
            # If title is default, generate a new one
            if title == "Generated Content":
                title = await self.generate_title(message)
            
            # Format the message with HTML paragraph tags
            message_html = f'<p>{message}</p>'
            
            # Handle file upload if provided
            if file_content and file_name:
                try:
                    # Step 1: Request file upload URL
                    pre_upload_response = await self.session.post(
                        f"{self.base_url}/api/v1/courses/{course_id}/files",
                        headers=self.headers,
                        json={
                            'name': file_name,
                            'size': len(file_content),
                            'content_type': 'application/octet-stream',
                            'parent_folder_path': 'announcement_uploads'
                        }
                    )
                    
                    if pre_upload_response.status != 200:
                        logger.error(f"Failed to get upload URL: {await pre_upload_response.text()}")
                        return {"error": "Failed to get file upload URL"}
                        
                    upload_data = await pre_upload_response.json()
                    upload_url = upload_data.get('upload_url')
                    
                    if not upload_url:
                        return {"error": "No upload URL provided by Canvas"}
                    
                    # Step 2: Upload file content
                    form = aiohttp.FormData()
                    form.add_field('file', 
                                 file_content,
                                 filename=file_name,
                                 content_type='application/octet-stream')
                    
                    async with self.session.post(
                        upload_url,
                        headers={'Authorization': self.headers['Authorization']},
                        data=form
                    ) as upload_response:
                        if upload_response.status in [200, 201]:
                            file_data = await upload_response.json()
                            file_id = file_data.get('id')
                            
                            # Step 3: Get file info to get the proper URL
                            async with self.session.get(
                                f"{self.base_url}/api/v1/files/{file_id}",
                                headers=self.headers
                            ) as file_info_response:
                                if file_info_response.status == 200:
                                    file_info = await file_info_response.json()
                                    file_url = file_info.get('url')
                                    if file_url:
                                        message_html += (
                                            f'\n\n<p>Attached file: <a href="{file_url}" '
                                            f'target="_blank">{file_name}</a></p>'
                                        )
                                else:
                                    logger.error("Failed to get file info")
                        else:
                            logger.error(f"File upload failed: {await upload_response.text()}")
                            return {"error": "Failed to upload file"}
                            
                except Exception as upload_error:
                    logger.error(f"Error during file upload: {str(upload_error)}")
                    return {"error": f"File upload error: {str(upload_error)}"}
            
            # Create the announcement
            payload = {
                'title': title,
                'message': message_html,
                'is_announcement': True,
                'published': is_published,
                'allow_rating': True,
                'specific_sections': 'all',
                'delayed_post_at': None,
                'require_initial_post': False
            }
            
            async with self.session.post(
                f"{self.base_url}/api/v1/courses/{course_id}/discussion_topics",
                headers=self.headers,
                json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "announcement_id": result.get('id'),
                        "title": result.get('title'),
                        "message": result.get('message'),
                        "published": result.get('published')
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to create announcement. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Failed to create announcement: {error_text}"}
                    
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