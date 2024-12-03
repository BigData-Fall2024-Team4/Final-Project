from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import boto3
import requests
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

from env_var import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    AWS_BUCKET_NAME
)

# Default arguments for the DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
}

# Setup Selenium WebDriver
def setup_webdriver():
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--headless")
    return webdriver.Chrome(options=chrome_options)

# Task 1: Scrape metadata and save it to S3
def scrape_metadata_to_s3(**kwargs):
    driver = setup_webdriver()
    base_url = "https://link.springer.com/search?facet-content-type=%22Book%22&package=openaccess&facet-language=%22En%22&facet-sub-discipline=%22Artificial+Intelligence%22&facet-discipline=%22Computer+Science%22"
    books = []

    try:
        driver.get(base_url)
        time.sleep(5)
        book_elements = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.title"))
        )
        for element in book_elements:
            title = element.text.strip()
            href = element.get_attribute('href')
            if title and href:
                books.append({'title': title, 'url': href})
    finally:
        driver.quit()

    # Save metadata to S3
    metadata_file = 'metadata.json'
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
    with open(metadata_file, 'w') as file:
        json.dump(books, file)
    s3_client.upload_file(metadata_file, AWS_BUCKET_NAME, metadata_file)

    return "Metadata successfully scraped and uploaded to S3."

# Task 2: Download PDFs using the metadata
def download_pdfs(**kwargs):
    # Download metadata from S3
    metadata_file = 'metadata.json'
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
    s3_client.download_file(AWS_BUCKET_NAME, metadata_file, metadata_file)

    with open(metadata_file, 'r') as file:
        books = json.load(file)

    driver = setup_webdriver()
    for book in books:
        try:
            driver.get(book['url'])
            time.sleep(2)
            pdf_link = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.c-pdf-download.u-clear-both a"))
            )
            pdf_url = pdf_link.get_attribute('href')
            response = requests.get(pdf_url, timeout=30)
            if response.status_code == 200:
                pdf_file = f"{book['title'].replace(' ', '_')}.pdf"
                with open(pdf_file, 'wb') as file:
                    file.write(response.content)
                # Upload PDF to S3
                s3_client.upload_file(pdf_file, AWS_BUCKET_NAME, f"pdfs/{pdf_file}")
        except Exception as e:
            print(f"Error processing {book['title']}: {e}")
    driver.quit()

    return "PDFs downloaded and uploaded to S3."

# Task 3: Extract titles and summaries and upload to S3
def extract_titles_and_summaries(**kwargs):
    # Download metadata from S3
    metadata_file = 'metadata.json'
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
    s3_client.download_file(AWS_BUCKET_NAME, metadata_file, metadata_file)

    with open(metadata_file, 'r') as file:
        books = json.load(file)

    summaries = []
    driver = setup_webdriver()
    for book in books:
        try:
            driver.get(book['url'])
            time.sleep(2)
            summary_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.abstract-content"))
            )
            summary = summary_element.text.strip()
            summaries.append({'title': book['title'], 'summary': summary})
        except Exception as e:
            print(f"Error extracting summary for {book['title']}: {e}")
    driver.quit()

    # Save summaries to S3
    summaries_file = 'summaries.json'
    with open(summaries_file, 'w') as file:
        json.dump(summaries, file)
    s3_client.upload_file(summaries_file, AWS_BUCKET_NAME, summaries_file)

    return "Summaries successfully extracted and uploaded to S3."

# Define the DAG
with DAG(
    'springer_scraper',
    default_args=default_args,
    description='Scrape Springer Books, Download PDFs, and Extract Summaries',
    schedule_interval=timedelta(days=1),
    start_date=datetime(2024, 11, 1),
    catchup=False,
) as dag:
    task_scrape_metadata = PythonOperator(
        task_id='scrape_metadata_to_s3',
        python_callable=scrape_metadata_to_s3,
        provide_context=True
    )

    task_download_pdfs = PythonOperator(
        task_id='download_pdfs',
        python_callable=download_pdfs,
        provide_context=True
    )

    task_extract_summaries = PythonOperator(
        task_id='extract_titles_and_summaries',
        python_callable=extract_titles_and_summaries,
        provide_context=True
    )

    # Define task dependencies
    task_scrape_metadata >> task_download_pdfs >> task_extract_summaries