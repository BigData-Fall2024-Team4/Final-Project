from web_agent.query import query_web_agent

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