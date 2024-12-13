import boto3
from botocore.exceptions import ClientError
import logging
from typing import List, Dict
from pydantic import BaseModel

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
        for obj in objects:
            key = obj['Key']
            if key.startswith(f'{self.books_folder}/'):
                parts = key[len(f'{self.books_folder}/'):].split('/')
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

    async def close(self):
        """Cleanup method"""
        if hasattr(self, 's3_client'):
            self.s3_client.close()
        logger.info("PDF listing agent closed")