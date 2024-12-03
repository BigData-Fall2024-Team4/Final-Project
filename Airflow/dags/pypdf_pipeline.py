from env_var import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY, 
    AWS_REGION,
    AWS_BUCKET_NAME
)

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.utils.task_group import TaskGroup
from datetime import datetime, timedelta
from pathlib import Path
import logging
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
import tempfile
import fitz  # PyMuPDF
import tabula
import pandas as pd
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class PDFProcessor:
    def __init__(self):
        config = Config(
            retries=dict(max_attempts=3),
            connect_timeout=5,
            read_timeout=5
        )
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
            config=config
        )
        self.bucket_name = AWS_BUCKET_NAME

    def format_table(self, df):
        """Format DataFrame as inline text with delimiters"""
        if df.empty:
            return ""
        
        table_str = "\n[TABLE_START]\n"
        headers = " | ".join(str(col) for col in df.columns)
        table_str += headers + "\n"
        table_str += "-" * len(headers) + "\n"
        
        for _, row in df.iterrows():
            row_str = " | ".join(str(val) for val in row.values)
            table_str += row_str + "\n"
        
        table_str += "[TABLE_END]\n"
        return table_str

    def extract_tables_from_page(self, pdf_path, page_number):
        """Extract tables from a specific page"""
        try:
            tables = tabula.read_pdf(
                pdf_path,
                pages=page_number + 1,
                multiple_tables=True,
                guess=True,
                silent=True,
                lattice=True,
                stream=True
            )
            return tables
        except Exception as e:
            logger.error(f"Error extracting tables from page {page_number}: {str(e)}")
            return []

    def process_pdf(self, s3_input_key):
        try:
            logger.info(f"Starting to process file: {s3_input_key}")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)
                
                path_parts = Path(s3_input_key).parts
                book_folder = path_parts[-2]
                original_filename = path_parts[-1]
                filename_stem = Path(original_filename).stem
                
                input_file = temp_dir_path / original_filename
                logger.info(f"Downloading file from S3: {s3_input_key}")
                self.s3_client.download_file(
                    self.bucket_name,
                    s3_input_key,
                    str(input_file)
                )
                
                output_base_dir = temp_dir_path / book_folder / "output"
                output_dir = output_base_dir
                images_dir = output_base_dir / "images"
                output_dir.mkdir(parents=True, exist_ok=True)
                images_dir.mkdir(parents=True, exist_ok=True)
                
                text_file_path = output_dir / f"{filename_stem}.txt"
                image_list_path = output_dir / f"{filename_stem}_image_list.txt"
                
                logger.info(f"Opening PDF document: {input_file}")
                pdf_document = fitz.open(str(input_file))
                image_counter = 0
                table_counter = 0
                
                with open(text_file_path, 'w', encoding='utf-8') as text_file, \
                     open(image_list_path, 'w', encoding='utf-8') as image_list_file:
                    
                    text_file.write(f"{filename_stem}\n{'='*len(filename_stem)}\n\n")
                    
                    for page_num in range(len(pdf_document)):
                        logger.info(f"Processing page {page_num + 1}")
                        page = pdf_document[page_num]
                        text_file.write(f"\nPage {page_num + 1}\n{'-'*10}\n")
                        
                        text = page.get_text()
                        if text.strip():
                            text_file.write(text.strip() + "\n")
                        
                        tables = self.extract_tables_from_page(str(input_file), page_num)
                        for table in tables:
                            if not isinstance(table, pd.DataFrame) or table.empty:
                                continue
                            table_counter += 1
                            logger.info(f"Found table {table_counter} on page {page_num + 1}")
                            table_text = self.format_table(table)
                            text_file.write(f"\nTable {table_counter}:{table_text}")
                        
                        images = page.get_images()
                        for img_index, img in enumerate(images):
                            try:
                                image_counter += 1
                                logger.info(f"Processing image {image_counter} on page {page_num + 1}")
                                xref = img[0]
                                base_image = pdf_document.extract_image(xref)
                                image_bytes = base_image["image"]
                                image_ext = base_image["ext"]
                                
                                image_filename = f"{filename_stem}_image{image_counter}.{image_ext}"
                                image_path = images_dir / image_filename
                                
                                with open(image_path, "wb") as image_file:
                                    image_file.write(image_bytes)
                                
                                s3_image_key = f"{book_folder}/output/images/{image_filename}"
                                self.s3_client.upload_file(
                                    str(image_path),
                                    self.bucket_name,
                                    s3_image_key
                                )
                                
                                image_list_file.write(f"Page {page_num + 1}: {s3_image_key}\n")
                                text_file.write(f"\n[Image {image_counter}: {image_filename}]\n")
                                
                                image_path.unlink()
                                
                            except Exception as e:
                                logger.error(f"Failed to process image {image_counter}: {str(e)}")
                                continue
                        
                        text_file.write("\n" + "-"*40 + "\n")
                    
                    pdf_document.close()
                
                text_s3_key = f"{book_folder}/output/{filename_stem}.txt"
                image_list_s3_key = f"{book_folder}/output/{filename_stem}_image_list.txt"
                
                logger.info(f"Uploading processed files to S3")
                self.s3_client.upload_file(
                    str(text_file_path),
                    self.bucket_name,
                    text_s3_key
                )
                
                self.s3_client.upload_file(
                    str(image_list_path),
                    self.bucket_name,
                    image_list_s3_key
                )
                
                logger.info(f"Successfully processed {original_filename}")
                return {
                    'text_file': text_s3_key,
                    'image_list': image_list_s3_key,
                    'image_count': image_counter,
                    'table_count': table_counter
                }
                
        except Exception as e:
            logger.error(f"Error processing document {s3_input_key}: {str(e)}")
            logger.exception("Full error traceback:")
            raise

    def list_pdf_files(self):
        try:
            logger.info("Listing PDF files from S3")
            all_pdf_files = []
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix='springer_books/'
            )
            
            for page in pages:
                for obj in page.get('Contents', []):
                    if obj['Key'].lower().endswith('.pdf'):
                        all_pdf_files.append(obj['Key'])
            
            if not all_pdf_files:
                logger.warning("No PDF files found in springer_books/")
            else:
                all_pdf_files.sort()
                all_pdf_files = all_pdf_files[:5]
                logger.info(f"Found {len(all_pdf_files)} PDF files to process")
            
            return all_pdf_files
                
        except ClientError as e:
            logger.error(f"Error listing PDF files: {str(e)}")
            raise

def list_pdfs(**context):
    logger.info("Starting PDF listing task")
    processor = PDFProcessor()
    pdf_files = processor.list_pdf_files()
    if not pdf_files:
        raise ValueError("No PDF files found")
    
    logger.info(f"Found {len(pdf_files)} PDF files")
    context['task_instance'].xcom_push(key='pdf_files', value=pdf_files)
    return pdf_files

def process_single_pdf(pdf_file, **context):
    logger.info(f"Starting to process PDF: {pdf_file}")
    processor = PDFProcessor()
    try:
        result = processor.process_pdf(pdf_file)
        logger.info(f"Successfully processed PDF: {pdf_file}")
        return {
            'input_file': pdf_file,
            'output_files': result,
            'status': 'success'
        }
    except Exception as e:
        logger.error(f"Error processing PDF {pdf_file}: {str(e)}")
        return {
            'input_file': pdf_file,
            'error': str(e),
            'status': 'failed'
        }

def save_results(**context):
    logger.info("Starting to save processing results")
    ti = context['task_instance']
    pdf_files = ti.xcom_pull(task_ids='list_pdfs', key='pdf_files')
    results = []
    
    for pdf_file in pdf_files:
        result = ti.xcom_pull(task_ids=f'process_pdfs.process_pdf_{pdf_files.index(pdf_file)}')
        results.append(result)
    
    with open('processing_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    success_count = sum(1 for r in results if r['status'] == 'success')
    logger.info(f"\nProcessing Summary:")
    logger.info(f"Successfully processed: {success_count} files")
    logger.info(f"Failed to process: {len(results) - success_count} files")
    
    for result in results:
        if result['status'] == 'success':
            logger.info(f"✓ Processed {result['input_file']}")
            logger.info(f"  - Text file: {result['output_files']['text_file']}")
            logger.info(f"  - Images found: {result['output_files']['image_count']}")
            logger.info(f"  - Tables found: {result['output_files']['table_count']}")
        else:
            logger.error(f"✗ Failed to process {result['input_file']}: {result['error']}")

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'pdf_processing_pipeline',
    default_args=default_args,
    description='Process PDFs from S3 bucket',
    schedule_interval=timedelta(days=1),
    catchup=False
) as dag:
    
    list_pdfs_task = PythonOperator(
        task_id='list_pdfs',
        python_callable=list_pdfs,
        provide_context=True,
    )
    
    with TaskGroup(group_id='process_pdfs') as process_group:
        def create_process_task(pdf_file_idx):
            return PythonOperator(
                task_id=f'process_pdf_{pdf_file_idx}',
                python_callable=process_single_pdf,
                op_kwargs={
                    'pdf_file': f"{{{{ task_instance.xcom_pull(task_ids='list_pdfs')[{pdf_file_idx}] }}}}"
                },
                provide_context=True,
            )
        
        process_tasks = [create_process_task(i) for i in range(5)]
    
    save_results_task = PythonOperator(
        task_id='save_results',
        python_callable=save_results,
        provide_context=True,
    )
    
    # Set dependencies
    list_pdfs_task >> process_group >> save_results_task