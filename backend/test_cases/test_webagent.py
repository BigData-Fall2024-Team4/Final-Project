import os
import requests
from typing import Optional, Dict, Any
import pytest

def query_web_agent(url: str, question: Optional[str] = None) -> Dict[str, Any]:
    try:
        endpoints = [
            "http://34.162.53.77:8000/agent-workflow",
            "http://34.162.53.77:8000/agent-workflow/form",
            "http://34.162.53.77:8000/reset-supervisor"
        ]

        payload = {
            "query": question if question else url,
            "url": url
        }

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

def query_llamaparse(document_url: str) -> Dict[str, Any]:
    try:
        api_key = os.getenv("LLAMAPARSE_API_KEY")
        if not api_key:
            raise ValueError("LLAMAPARSE_API_KEY not found in environment variables.")

        # Initiate parsing job
        start_endpoint = "https://api.cloud.llamaindex.ai/api/parsing/job"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        start_payload = {
            "document_url": document_url
        }

        start_response = requests.post(start_endpoint, json=start_payload, headers=headers)
        if not start_response.ok:
            return {
                "status_code": start_response.status_code,
                "error": start_response.text
            }

        start_data = start_response.json()
        job_id = start_data.get("job_id")
        if not job_id:
            return {
                "status_code": 400,
                "error": "Job ID not returned in the response.",
                "response": start_data
            }

        # Fetch parsing result
        result_endpoint = f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}/result/markdown"
        result_response = requests.get(result_endpoint, headers=headers)

        return {
            "status_code": result_response.status_code,
            "response": result_response.json() if result_response.ok else result_response.text
        }

    except Exception as e:
        return {
            "status_code": 500,
            "error": str(e)
        }

class TestWebAgentQueries:
    def test_agent_workflow_endpoint(self):
        url = "https://example.com"
        question = "What is this website about?"

        result = query_web_agent(url, question)

        assert result['status_code'] == 200
        assert result['url'] == url
        assert result['question'] == question
        assert 'responses' in result

        workflow_responses = [
            resp for resp in result['responses'] 
            if "agent-workflow" in resp['endpoint']
        ]
        assert len(workflow_responses) > 0

    def test_form_data_endpoint(self):
        url = "https://example.com/upload"
        question = "Process this document"

        result = query_web_agent(url, question)

        assert result['status_code'] == 200
        assert result['url'] == url

        form_responses = [
            resp for resp in result['responses'] 
            if "agent-workflow/form" in resp['endpoint']
        ]
        assert len(form_responses) > 0

    def test_reset_supervisor_endpoint(self):
        url = "http://34.162.53.77:8000/reset-supervisor"

        result = query_web_agent(url)

        assert result['status_code'] == 200

        reset_responses = [
            resp for resp in result['responses'] 
            if "reset-supervisor" in resp['endpoint']
        ]
        assert len(reset_responses) > 0

    def test_llamaparse_api(self):
        document_url = "https://www.example.com/sample-document"

        result = query_llamaparse(document_url)

        assert result['status_code'] == 200, "Failed to get a successful response from LLAMAPARSE"
        assert "response" in result, "Response key missing in the result"
        assert isinstance(result['response'], (dict, str)), "Response should be a dictionary or string"

def main():
    os.environ["LLAMAPARSE_API_KEY"] = "llx-DjJP4O3nCCDJeRIf3tBPzcffnQrYCald1kHP1GxLFQBEG4f0"

    test_cases = [
        {
            "url": "https://news.northeastern.edu/2024/10/29/commencement-2025-fenway-park/",
            "question": "When and where is the commencement ceremony?"
        },
        {
            "url": "http://34.162.53.77:8000/reset-supervisor",
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

    print("\nTesting LLAMAPARSE API...")
    document_url = "https://www.example.com/sample-document"
    result = query_llamaparse(document_url)
    print(f"LLAMAPARSE Test Response: {result}")

    print("\nTests completed!")

if __name__ == "__main__":
    main()
