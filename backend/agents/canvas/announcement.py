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


    async def _format_content_with_llm(self, content: str) -> str:
        """Use LLM to format content for Canvas announcement with improved table and typography handling"""
        try:
            llm = ChatOpenAI()
            
            prompt = f"""Format the following content for a Canvas LMS announcement, paying special attention to tables and typography.

Rules for formatting:
1. Tables:
   - Must be enclosed in proper <table> tags
   - Each row must use <tr> tags
   - Headers must use <th> tags
   - Data cells must use <td> tags
   - Add borders and padding for readability
   - Tables must be responsive

2. Typography:
   - Base font size should be 14px
   - Headers should use relative sizes:
     * h1: 20px
     * h2: 16px
     * h3: 12px
   - Line height should be 1.5
   - Use Arial or sans-serif fonts

3. Structure:
   - Each section should be clearly separated
   - Numbered lists should use <ol> tags
   - Add appropriate spacing between elements
   - Preserve document hierarchy

Here's the content to format:
{content}

Required HTML structure:
<div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #333;">
  [Main content here with all headers, tables, and lists properly formatted]
</div>

Tables should follow this structure:
<div style="overflow-x: auto;">
  <table style="border-collapse: collapse; width: 100%; margin: 15px 0;">
    <thead>
      <tr>
        <th style="border: 1px solid #ddd; padding: 8px; background-color: #f5f6fa;">[header]</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="border: 1px solid #ddd; padding: 8px;">[data]</td>
      </tr>
    </tbody>
  </table>
</div>

Return ONLY the formatted HTML, no explanations. Ensure all tables are properly formatted with the exact structure shown above."""

            formatted_content = await llm.apredict(prompt)
            
            # Ensure proper wrapping if LLM didn't provide it
            if not formatted_content.strip().startswith('<div'):
                formatted_content = f'''
                    <div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #333;">
                        {formatted_content}
                    </div>
                '''
            
            return formatted_content.strip()
            
        except Exception as e:
            logger.error(f"Error formatting content with LLM: {str(e)}")
            # Fallback basic formatting with table detection
            try:
                # Basic table detection and formatting
                lines = content.split('\n')
                formatted_lines = []
                in_table = False
                current_table = []
                
                for line in lines:
                    if '|' in line:
                        if not in_table:
                            in_table = True
                            current_table = []
                        current_table.append(line)
                    else:
                        if in_table:
                            # Format collected table
                            table_html = self._format_basic_table('\n'.join(current_table))
                            formatted_lines.append(table_html)
                            in_table = False
                            current_table = []
                        formatted_lines.append(f'<p style="margin: 10px 0;">{line}</p>')
                
                # Handle any remaining table
                if current_table:
                    table_html = self._format_basic_table('\n'.join(current_table))
                    formatted_lines.append(table_html)
                
                return f'''
                    <div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #333;">
                        {'\n'.join(formatted_lines)}
                    </div>
                '''
            except:
                # Ultimate fallback
                return f'''
                    <div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #333;">
                        {content}
                    </div>
                '''

    def _format_basic_table(self, table_content: str) -> str:
        """Basic table formatting for fallback case"""
        lines = [line.strip() for line in table_content.split('\n') if line.strip()]
        headers = [cell.strip() for cell in lines[0].split('|')[1:-1]]
        
        html = '''
        <div style="overflow-x: auto;">
            <table style="border-collapse: collapse; width: 100%; margin: 15px 0;">
                <thead>
                    <tr>
        '''
        
        # Add headers
        for header in headers:
            html += f'<th style="border: 1px solid #ddd; padding: 8px; background-color: #f5f6fa;">{header}</th>'
        
        html += '</tr></thead><tbody>'
        
        # Add data rows (skip header and separator rows)
        for line in lines[2:]:
            if not line.strip().startswith('|-'):
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                html += '<tr>'
                for cell in cells:
                    html += f'<td style="border: 1px solid #ddd; padding: 8px;">{cell}</td>'
                html += '</tr>'
        
        html += '</tbody></table></div>'
        return html

    async def create_announcement(self, course_id: str, title: str, message: str, 
                                    is_published: bool = True, file_content: bytes = None,
                                    file_name: str = None) -> Dict[str, Any]:
            """Create a course announcement with optional file attachment"""
            try:
                await self._ensure_session()
                
                # If title is default, generate a new one
                if title == "Generated Content":
                    title = await self.generate_title(message)
                
                # Format message using LLM
                formatted_message = await self._format_content_with_llm(message)
                
                # Handle file upload if provided
                if file_content and file_name:
                    try:
                        # Your existing file upload code...
                        upload_result = await self._handle_file_upload(course_id, file_content, file_name)
                        if upload_result.get('file_url'):
                            # Add file link to the formatted message
                            file_link = (
                                f'<div style="margin-top: 20px; padding: 10px; '
                                f'border: 1px solid #e0e0e0; border-radius: 4px;">'
                                f'<p style="margin: 0;">Attached file: '
                                f'<a href="{upload_result["file_url"]}" '
                                f'target="_blank" style="color: #3498db;">{file_name}</a></p></div>'
                            )
                            formatted_message += file_link
                    except Exception as upload_error:
                        logger.error(f"Error during file upload: {str(upload_error)}")
                        return {"error": f"File upload error: {str(upload_error)}"}
                
                # Create the announcement with formatted message
                payload = {
                    'title': title,
                    'message': formatted_message,
                    'is_announcement': True,
                    'published': is_published,
                    'allow_rating': True,
                    'specific_sections': 'all',
                    'delayed_post_at': None,
                    'require_initial_post': False
                }
                
                # Your existing announcement creation code...
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