import requests
import json
from typing import Optional

def query_web_agent(query: str) -> None:
    """Query the web agent with user input"""
    try:
        # Make the request
        response = requests.post(
            "http://localhost:8000/agent-workflow",
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        
        # Print divider and query
        print("\n" + "="*80)
        print(f"\nQuery: {query}")
        
        # Print response
        if response.status_code == 200:
            result = response.json()
            print("\nResponse:")
            print(result.get('response', 'No response content'))
        else:
            print(f"\nError: Status code {response.status_code}")
            print(response.text)
        
        print("\n" + "="*80)

    except Exception as e:
        print(f"\nError occurred: {str(e)}")

def main():
    print("\nWelcome to Web Agent Test System!")
    print("Type 'exit' to quit")
    print("You can ask questions or provide URLs")
    
    while True:
        query = input("\nEnter your query: ").strip()
        
        if query.lower() == 'exit':
            print("\nGoodbye!")
            break
        
        if query:
            query_web_agent(query)

if __name__ == "__main__":
    main()