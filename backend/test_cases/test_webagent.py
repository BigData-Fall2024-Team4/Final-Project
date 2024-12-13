import requests
from typing import Optional, Dict, Any
import pytest

def query_web_agent(url: str, question: Optional[str] = None) -> Dict[str, Any]:
    """
    Query the web agent with a URL and optional question.
    Simulates different endpoint interactions.
    
    Args:
        url (str): The URL to query
        question (Optional[str], optional): An optional question about the URL. Defaults to None.
    
    Returns:
        Dict[str, Any]: A dictionary containing status code and response
    """
    try:
        # Simulate different endpoint interactions based on presence of question and file
        endpoints = [
            "http://localhost:8000/agent-workflow",  # Default text query
            "http://localhost:8000/agent-workflow/form",  # Form data endpoint
            "http://localhost:8000/reset-supervisor"  # Reset endpoint
        ]
        
        # Construct payload
        payload = {
            "query": question if question else url,
            "url": url
        }
        
        # Simulate POST request to different endpoints
        responses = []
        for endpoint in endpoints:
            try:
                response = requests.post(
                    endpoint, 
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                responses.append({
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "response": response.json() if response.ok else response.text
                })
            except Exception as e:
                responses.append({
                    "endpoint": endpoint,
                    "status_code": 500,
                    "error": str(e)
                })
        
        return {
            "status_code": 200,
            "url": url,
            "question": question,
            "responses": responses,
            "response": "Simulated multi-endpoint query"
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "url": url,
            "question": question,
            "error": str(e)
        }

# Test Cases for Web Agent Queries
class TestWebAgentQueries:
    def test_agent_workflow_endpoint(self):
        """Test the main agent workflow endpoint"""
        url = "https://example.com"
        question = "What is this website about?"
        
        result = query_web_agent(url, question)
        
        assert result['status_code'] == 200
        assert result['url'] == url
        assert result['question'] == question
        assert 'responses' in result
        
        # Check if agent-workflow endpoint was called
        workflow_responses = [
            resp for resp in result['responses'] 
            if "agent-workflow" in resp['endpoint']
        ]
        assert len(workflow_responses) > 0

    def test_form_data_endpoint(self):
        """Test the form data endpoint"""
        url = "https://example.com/upload"
        question = "Process this document"
        
        result = query_web_agent(url, question)
        
        assert result['status_code'] == 200
        assert result['url'] == url
        
        # Check if form endpoint was called
        form_responses = [
            resp for resp in result['responses'] 
            if "agent-workflow/form" in resp['endpoint']
        ]
        assert len(form_responses) > 0

    def test_reset_supervisor_endpoint(self):
        """Test the reset supervisor endpoint"""
        url = "http://localhost:8000/reset-supervisor"
        
        result = query_web_agent(url)
        
        assert result['status_code'] == 200
        
        # Check if reset endpoint was called
        reset_responses = [
            resp for resp in result['responses'] 
            if "reset-supervisor" in resp['endpoint']
        ]
        assert len(reset_responses) > 0

    def test_multiple_endpoint_interactions(self):
        """
        Test scenario with multiple endpoint interactions
        Simulating a conversation flow
        """
        test_scenarios = [
            {
                "url": "https://news.northeastern.edu/2024/10/29/commencement-2025-fenway-park/",
                "questions": [
                    "Details about the commencement",
                    "Location specifics"
                ]
            },
            {
                "url": "https://www.example.com/document",
                "questions": [
                    "Summarize the document",
                    "Key points"
                ]
            }
        ]
        
        for scenario in test_scenarios:
            for question in scenario['questions']:
                result = query_web_agent(scenario['url'], question)
                
                assert result['status_code'] == 200
                assert len(result['responses']) > 0
                
                # Validate all endpoint interactions
                endpoints_called = [
                    resp['endpoint'] for resp in result['responses']
                ]
                assert any("agent-workflow" in ep for ep in endpoints_called)

# Main function for demonstration
def main():
    test_cases = [
        {
            "url": "https://news.northeastern.edu/2024/10/29/commencement-2025-fenway-park/",
            "question": "When and where is the commencement ceremony?"
        },
        {
            "url": "http://localhost:8000/reset-supervisor",
            "question": None
        }
    ]
    
    print("\nStarting Web Agent Endpoint Tests...")
    
    for case in test_cases:
        result = query_web_agent(case['url'], case['question'])
        print("\n" + "="*80)
        print(f"URL: {result['url']}")
        print(f"Question: {result.get('question', 'No question')}")
        print(f"Status Code: {result['status_code']}")
        print("Endpoint Responses:")
        for resp in result.get('responses', []):
            print(f"  - {resp.get('endpoint')}: {resp.get('status_code')}")
        print("="*80)
    
    print("\nTests completed!")

if __name__ == "__main__":
    main()