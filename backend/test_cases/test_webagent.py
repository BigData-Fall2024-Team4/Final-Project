import pytest
from fastapi.testclient import TestClient
from main_fastapi import app

client = TestClient(app)

def test_web_agent_health():
    """Test if web agent endpoint is accessible"""
    response = client.get("/health")
    assert response.status_code == 200

def test_web_agent_query():
    """Test if web agent can process a simple query"""
    test_data = {
        "query": "What is the weather today?"
    }
    
    response = client.post("/agent-workflow", json=test_data)
    assert response.status_code == 200
    assert "response" in response.json()

def test_invalid_query():
    """Test web agent's handling of invalid query"""
    test_data = {
        "query": ""  # Empty query
    }
    
    response = client.post("/agent-workflow", json=test_data)
    assert response.status_code == 422  # FastAPI validation error

def test_web_agent_large_query():
    """Test web agent with a longer query"""
    test_data = {
        "query": "Tell me about the history of artificial intelligence and its major developments"
    }
    
    response = client.post("/agent-workflow", json=test_data)
    assert response.status_code == 200
    assert len(response.json()["response"]) > 0

if __name__ == "__main__":
    pytest.main(["-v"])