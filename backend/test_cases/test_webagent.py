import requests
from typing import Optional, Dict, Any
import pytest

def query_web_agent(url: str, question: Optional[str] = None) -> Dict[str, Any]:
    """
    Query the web agent with a URL and optional question.
    Returns a dictionary with status code and a default response.
    
    Args:
        url (str): The URL to query
        question (Optional[str], optional): An optional question about the URL. Defaults to None.
    
    Returns:
        Dict[str, Any]: A dictionary containing status code and response
    """
    try:
        # Construct the query
        if question:
            query = f"{question} {url}"
        else:
            query = url
        
        # Return a mock response
        return {
            "status_code": 200,
            "url": url,
            "question": question,
            "response": "This is a default text response. No actual web query was made."
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "url": url,
            "question": question,
            "error": str(e)
        }

# Pytest test cases
def test_query_web_agent_with_question():
    url = "https://example.com"
    question = "What is this website about?"
    
    result = query_web_agent(url, question)
    
    assert result['status_code'] == 200
    assert result['url'] == url
    assert result['question'] == question
    assert 'response' in result

def test_query_web_agent_without_question():
    url = "https://example.com"
    
    result = query_web_agent(url)
    
    assert result['status_code'] == 200
    assert result['url'] == url
    assert result['question'] is None
    assert 'response' in result

# Optional: Main function for demonstration
def main():
    # Test cases
    test_cases = [
        {
            "url": "https://news.northeastern.edu/2024/10/29/commencement-2025-fenway-park/",
            "question": "When and where is the commencement ceremony?"
        },
        {
            "url": "https://news.northeastern.edu/2024/10/29/commencement-2025-fenway-park/",
            "question": None
        },
        {
            "url": "https://www.python.org/about/",
            "question": "What are the key features of Python?"
        }
    ]
    
    print("\nStarting Web Agent Tests...")
    
    for case in test_cases:
        result = query_web_agent(case['url'], case['question'])
        print("\n" + "="*80)
        print(f"URL: {result['url']}")
        print(f"Question: {result.get('question', 'No question')}")
        print(f"Status Code: {result['status_code']}")
        print(f"Response: {result.get('response', result.get('error', 'No response'))}")
        print("="*80)
    
    print("\nTests completed!")

if __name__ == "__main__":
    main()