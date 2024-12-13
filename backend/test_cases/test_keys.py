import os
from dotenv import load_dotenv
import requests
import boto3
from pinecone import Index

load_dotenv()

def check_openai_api_key():
    """Check if the OpenAI API key works by sending a dummy request."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is missing.")
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get("https://api.openai.com/v1/models", headers=headers)
    if response.status_code != 200:
        raise EnvironmentError(
            f"OpenAI API key test failed: {response.status_code} - {response.text}"
        )
    print("OpenAI API key is valid!")

def check_canvas_api_key():
    """Check if the Canvas API key works by hitting the base URL."""
    api_key = os.getenv("CANVAS_API_KEY")
    base_url = os.getenv("CANVAS_BASE_URL")
    if not api_key or not base_url:
        raise EnvironmentError("CANVAS_API_KEY or CANVAS_BASE_URL is missing.")
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(f"{base_url}/api/v1/accounts", headers=headers)
    if response.status_code != 200:
        raise EnvironmentError(
            f"Canvas API key test failed: {response.status_code} - {response.text}"
        )
    print("Canvas API key is valid!")

def check_aws_keys():
    """Check if AWS keys work by listing S3 buckets."""
    access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    if not access_key_id or not secret_access_key:
        raise EnvironmentError("AWS keys are missing.")
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
        buckets = s3.list_buckets()
        print(f"AWS keys are valid! Found {len(buckets['Buckets'])} buckets.")
    except Exception as e:
        raise EnvironmentError(f"AWS keys test failed: {e}")

def check_pinecone_keys():
    """Check if Pinecone keys work by interacting with the index."""
    api_key = os.getenv("PINECONE_API_KEY")
    environment = os.getenv("PINECONE_ENVIRONMENT")
    index_name = os.getenv("PINECONE_INDEX_NAME")
    if not api_key or not environment or not index_name:
        raise EnvironmentError("Pinecone keys are missing.")
    try:
        Index(api_key=api_key, environment=environment)
        print("Pinecone keys are valid!")
    except Exception as e:
        raise EnvironmentError(f"Pinecone keys test failed: {e}")

if __name__ == "__main__":
    try:
        check_openai_api_key()
        check_canvas_api_key()
        check_aws_keys()
        check_pinecone_keys()
        print("All keys validated successfully!")
    except EnvironmentError as e:
        print(f"Key validation failed: {e}")
        exit(1)
