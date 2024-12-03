import os
import time
from datetime import datetime, timedelta
import requests
import json
import logging
from typing import List, Dict, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from bs4 import BeautifulSoup

from airflow import DAG
from airflow.operators.python import PythonOperator

# Import environment variables
from env_var import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    AWS_BUCKET_NAME
)

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_s3_client_with_time_correction():
    """
    Create S3 client with time correction to prevent skew errors
    """
    # Custom boto3 config to handle time-related issues
    config = Config(
        connect_timeout=30, 
        read_timeout=30, 
        retries={
            'max_attempts': 3,
            'mode': 'standard'
        }
    )
    
    # Create S3 client with precise time handling
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
        config=config
    )
    
    return s3_client

def generate_unique_s3_key(prefix: str, filename: str) -> str:
    """
    Generate a unique and safe S3 key
    """
    # Sanitize filename
    safe_filename = "".join(
        [c for c in filename if c.isalnum() or c in (' ', '_')]
    )[:50].strip()
    
    # Add timestamp to ensure uniqueness
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
    
    return f"{prefix}/{safe_filename}_{timestamp}.json"

def scrape_springer_books(**context) -> List[Dict]:
    """
    Scrape Springer books with robust error handling
    """
    base_url = "https://link.springer.com/search"
    params = {
        'facet-content-type': '"Book"',
        'package': 'openaccess',
        'facet-language': '"En"',
        'facet-sub-discipline': '"Artificial+Intelligence"',
        'facet-discipline': '"Computer+Science"'
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    }

    books = []
    try:
        for page in range(1, 4):  # Limit to first 3 pages
            params['page'] = page
            
            response = requests.get(
                base_url, 
                params=params, 
                headers=headers, 
                timeout=30
            )
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find book titles and links
                book_elements = soup.select('a.title')
                
                for element in book_elements:
                    title = element.get_text(strip=True)
                    href = element.get('href', '')
                    full_url = f"https://link.springer.com{href}"
                    
                    books.append({
                        'title': title,
                        'url': full_url
                    })
                
                logger.info(f"Page {page}: Found {len(book_elements)} books")
            else:
                logger.error(f"Failed to fetch page {page}. Status code: {response.status_code}")
    
    except Exception as e:
        logger.error(f"Scraping error: {e}")
    
    # Push to XCom
    context['task_instance'].xcom_push(key='books', value=books)
    return books

def process_books(**context):
    """
    Process scraped books and upload metadata to S3
    """
    books = context['task_instance'].xcom_pull(key='books', task_ids='scrape_springer_books')
    
    # Create S3 client
    s3_client = create_s3_client_with_time_correction()

    processed_books = []
    for book in books:
        try:
            metadata = {
                'title': book['title'],
                'url': book['url'],
                'processed_timestamp': datetime.utcnow().isoformat()
            }
            
            # Generate unique S3 key
            s3_key = generate_unique_s3_key(
                'springer_books', 
                book['title']
            )
            
            # Upload to S3 with error handling
            s3_client.put_object(
                Bucket=AWS_BUCKET_NAME,
                Key=s3_key,
                Body=json.dumps(metadata, indent=2).encode('utf-8'),
                ContentType='application/json'
            )
            
            processed_books.append(metadata)
            logger.info(f"Processed book: {book['title']}")
        
        except ClientError as e:
            logger.error(f"S3 Upload Error for {book.get('title', 'Unknown')}: {e}")
        except Exception as e:
            logger.error(f"Error processing book {book.get('title', 'Unknown')}: {e}")

    # Push processed books to XCom
    context['task_instance'].xcom_push(key='processed_books', value=processed_books)

def generate_scrape_report(**context):
    """
    Generate and upload a comprehensive scrape report
    """
    books = context['task_instance'].xcom_pull(key='books', task_ids='scrape_springer_books')
    processed_books = context['task_instance'].xcom_pull(key='processed_books', task_ids='process_books')
    
    # Create S3 client
    s3_client = create_s3_client_with_time_correction()

    report = {
        'total_books_scraped': len(books),
        'total_books_processed': len(processed_books),
        'timestamp': datetime.utcnow().isoformat()
    }

    # Generate unique report key
    report_key = generate_unique_s3_key(
        'springer_books/reports', 
        'scrape_report'
    )
    
    try:
        s3_client.put_object(
            Bucket=AWS_BUCKET_NAME,
            Key=report_key,
            Body=json.dumps(report, indent=2).encode('utf-8'),
            ContentType='application/json'
        )
        logger.info(f"Generated scrape report: {report}")
    except ClientError as e:
        logger.error(f"Failed to upload report: {e}")

# DAG Configuration
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'springer_books_scraper',
    default_args=default_args,
    schedule_interval='@weekly',
    catchup=False
) as dag:
    
    scrape_books_task = PythonOperator(
        task_id='scrape_springer_books',
        python_callable=scrape_springer_books,
        provide_context=True
    )

    process_books_task = PythonOperator(
        task_id='process_books',
        python_callable=process_books,
        provide_context=True
    )

    generate_report_task = PythonOperator(
        task_id='generate_scrape_report',
        python_callable=generate_scrape_report,
        provide_context=True
    )

    # Task Dependencies
    scrape_books_task >> process_books_task >> generate_report_task