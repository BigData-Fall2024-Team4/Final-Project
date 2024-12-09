import logging
from typing import Dict, Any, BinaryIO

logger = logging.getLogger(__name__)

class DocumentHandlerAgent:
    """Agent for handling uploaded files and passing them through the system"""
    
    def __init__(self):
        self.supported_extensions = [
            '.pdf', '.docx', '.jpg', '.jpeg', 
            '.png', '.csv', '.xlsx'
        ]
        
    async def process_file(self, file: BinaryIO, filename: str) -> Dict[str, Any]:
        """Process uploaded file"""
        try:
            # Read the file content
            file_content = file.read()
            file_extension = filename.lower().split('.')[-1] if '.' in filename else ''
            
            if f'.{file_extension}' not in self.supported_extensions:
                return {
                    "success": False,
                    "error": f"Unsupported file type: {file_extension}",
                    "content": None
                }
            
            return {
                "success": True,
                "content": file_content,
                "filename": filename,
                "file_type": file_extension
            }
                
        except Exception as e:
            logger.error(f"Error handling file: {str(e)}")
            return {
                "success": False,
                "error": f"Error handling file: {str(e)}",
                "content": None
            }

    async def close(self):
        """Cleanup method"""
        pass