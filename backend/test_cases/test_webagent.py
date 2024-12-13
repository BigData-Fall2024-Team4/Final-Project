from fastapi.testclient import TestClient
from main_fastapi import app

client = TestClient(app)

def test_agent_query():
    """Test query with empty string"""
    test_data = {
        "query": ""
    }
    response = client.post("/agent-workflow", json=test_data)
    assert response.status_code == 200  # Since your endpoint accepts empty queries

def test_agent_workflow():
    """Test with actual query"""
    test_data = {
        "query": "What is machine learning?"
    }
    response = client.post("/agent-workflow", json=test_data)
    assert response.status_code == 200