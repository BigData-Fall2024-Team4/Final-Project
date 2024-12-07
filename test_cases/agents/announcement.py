import aiohttp
import asyncio
import json

async def send_to_server(query: str, conversation_id: str = None):
    """Send query to server and return response"""
    async with aiohttp.ClientSession() as session:
        payload = {
            "message": query,
            "conversation_id": conversation_id
        }
        
        async with session.post(
            "http://localhost:8000/agent-workflow",
            json=payload
        ) as response:
            return await response.json()

async def main():
    conversation_id = None
    
    print("\nCanvas Integration Test")
    print("Enter your query (or 'quit' to exit):")
    
    while True:
        query = input("\n> ")
        if query.lower() == 'quit':
            break
            
        try:
            result = await send_to_server(query, conversation_id)
            conversation_id = result.get('conversation_id')
            
            print("\nResponse:")
            print(result.get('response', 'No response received'))
            
        except Exception as e:
            print(f"\nError: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())