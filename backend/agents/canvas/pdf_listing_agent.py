from typing import List, Dict, Optional
import boto3
from botocore.exceptions import ClientError
import logging
from pydantic import BaseModel
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BookFolder(BaseModel):
    """Model for book folder metadata"""
    name: str
    path: str
    last_modified: str

class PDFListingAgent:
    """Agent for listing book folders in S3"""
    
    def __init__(self, aws_access_key_id: str, aws_secret_access_key: str, bucket_name: str, 
                 books_folder: str, region_name: str = 'us-east-1'):
        self.bucket_name = bucket_name
        self.books_folder = books_folder
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=region_name
            )
            logger.info(f"Successfully initialized S3 client for bucket: {bucket_name}")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {str(e)}")
            raise

    def _extract_folder_names(self, objects: List[Dict]) -> List[str]:
        """Extract unique folder names from object list"""
        folders = set()
        prefix_length = len(f"{self.books_folder}/")
        for obj in objects:
            key = obj['Key']
            if key.startswith('springer_books/'):
                parts = key[len('springer_books/'):].split('/')
                if parts[0]:  # Ensure it's not empty
                    folders.add(parts[0])
        return sorted(list(folders))

    async def list_book_folders(self) -> Dict[str, any]:
        """List all book folders in the S3 bucket using pagination"""
        try:
            all_contents = []
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            # Use pagination to get all objects
            for page in paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=f'{self.books_folder}/'
            ):
                if 'Contents' in page:
                    all_contents.extend(page['Contents'])

            if not all_contents:
                return {
                    "success": True,
                    "folders": [],
                    "total_folders": 0
                }
            
            # Extract unique folder names
            folder_names = self._extract_folder_names(all_contents)
            
            folders = []
            for folder in folder_names:
                # Find the most recent modification time for files in this folder
                folder_files = [obj for obj in all_contents if obj['Key'].startswith(f'{self.books_folder}/{folder}/')]
                last_modified = max(file['LastModified'] for file in folder_files) if folder_files else all_contents[0]['LastModified']
                
                folders.append(BookFolder(
                    name=folder,
                    path=f"{self.books_folder}/{folder}",
                    last_modified=last_modified.strftime('%Y-%m-%d %H:%M:%S')
                ))
            
            return {
                "success": True,
                "folders": folders,
                "total_folders": len(folders)
            }
            
        except ClientError as e:
            error_message = f"Error listing book folders: {str(e)}"
            logger.error(error_message)
            return {
                "success": False,
                "error": error_message,
                "folders": [],
                "total_folders": 0
            }

    def _group_folders_by_category(self, folders: List[BookFolder]) -> Dict[str, List[BookFolder]]:
        """Group folders into categories based on common keywords"""
        categories = {
            "Artificial Intelligence": [],
            "Data Science": [],
            "Computer Science": [],
            "Mathematics": [],
            "Other": []
        }
        
        for folder in folders:
            name = folder.name.lower()
            if any(kw in name for kw in ["ai", "artificial intelligence", "machine learning"]):
                categories["Artificial Intelligence"].append(folder)
            elif any(kw in name for kw in ["data", "analytics", "statistics"]):
                categories["Data Science"].append(folder)
            elif any(kw in name for kw in ["computer", "programming", "software"]):
                categories["Computer Science"].append(folder)
            elif any(kw in name for kw in ["math", "numerical", "calculation"]):
                categories["Mathematics"].append(folder)
            else:
                categories["Other"].append(folder)
        
        return {k: v for k, v in categories.items() if v}  # Remove empty categories

    async def process_request(self, message: str) -> Dict[str, str]:
        """Process the incoming request to list book folders"""
        if message.lower().strip() == "show pdfs":
            result = await self.list_book_folders()
            
            if result["success"]:
                if result["total_folders"] == 0:
                    return {
                        "response": "No book folders found in the springer_books directory.",
                        "agent": "pdf_listing"
                    }
                
                # Group folders by category
                categorized_folders = self._group_folders_by_category(result["folders"])
                
                # Format the response
                response_parts = [
                    "📚 Available Books in Springer Collection 📚",
                    f"Total Books: {result['total_folders']}\n",
                    "Categories:",
                    "=" * 50  # Separator line
                ]
                
                # Counter for overall numbering
                counter = 1
                
                # Add folders by category
                for category, folders in categorized_folders.items():
                    response_parts.append(f"\n{category}:")
                    response_parts.append("-" * 40)  # Subsection separator
                    
                    for folder in folders:
                        response_parts.append(f"{counter}. {folder.name}")
                        counter += 1
                    
                    response_parts.append("")  # Empty line between categories
                
                # Add footer with instructions
                response_parts.extend([
                    "=" * 50,  # Bottom separator
                    "📖 To access a specific book, use: 'read <book number>'",
                    "🔍 For more details about a book, use: 'info <book number>'"
                ])
                
                # Join all parts with appropriate spacing
                response = "\n".join(response_parts)
                
            else:
                response = f"Error listing book folders: {result.get('error', 'Unknown error')}"
            
            return {
                "response": response,
                "agent": "pdf_listing"
            }
            
        return {
            "response": "Invalid command. Use 'show pdfs' to list available book folders.",
            "agent": "pdf_listing"
        }

    async def close(self):
        """Cleanup method"""
        if hasattr(self, 's3_client'):
            self.s3_client.close()
        logger.info("PDF listing agent closed")