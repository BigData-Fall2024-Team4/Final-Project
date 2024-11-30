import requests
import json
from typing import Optional

def query_web_agent(url: str, question: Optional[str] = None) -> None:
    """Query the web agent with a URL and optional question"""
    try:
        # Construct the query
        if question:
            query = f"{question} {url}"
        else:
            query = url
            
        # Make the request
        response = requests.post(
            "http://localhost:8000/agent-workflow",
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        
        # Print request details
        print("\n" + "="*80)
        print(f"URL: {url}")
        print(f"Question: {question if question else 'No question - getting content summary'}")
        
        # Print response
        if response.status_code == 200:
            result = response.json()
            print("\nResponse:")
            print(result.get('response', 'No response content'))
        else:
            print(f"\nError: Status code {response.status_code}")
            print(response.text)
        
        print("="*80)

    except Exception as e:
        print(f"Error occurred: {str(e)}")

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
        query_web_agent(case['url'], case['question'])
        
    print("\nTests completed!")

if __name__ == "__main__":
    main()