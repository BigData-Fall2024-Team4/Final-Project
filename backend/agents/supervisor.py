from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
import logging
from .web_agent import WebSearchAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Message(BaseModel):
    """Message model for communication between agents"""
    content: str
    type: str = "text"
    role: str  # 'user' or 'assistant'
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SupervisorState(BaseModel):
    """State management for the supervisor"""
    messages: List[Message] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    current_agent: Optional[str] = None

class CanvasGPTSupervisor:
    """Main supervisor class for orchestrating agent interactions"""
    
    def __init__(self, openai_api_key: str):
        self.llm = ChatOpenAI(api_key=openai_api_key)
        self.web_agent = WebSearchAgent()
        self.state = SupervisorState()
        logger.info("CanvasGPT Supervisor initialized")

    def _get_conversation_context(self, current_message: str) -> str:
        """Get relevant context from conversation history"""
        if not self.state.messages:  # If no messages in history
            return ""
            
        conversation_history = []
        for msg in self.state.messages[-5:]:  # Get last 5 messages for context
            if msg.role == "user":
                conversation_history.append(f"User: {msg.content}")
            else:
                conversation_history.append(f"Assistant: {msg.content}")
        
        conversation_context = "\n".join(conversation_history)
        
        if not conversation_context:  # If no valid context
            return ""
            
        context_prompt = f"""
        Previous conversation:
        {conversation_context}

        Current message: {current_message}
        """
        return context_prompt

    async def _route_message(self, message: str) -> str:
        """Determine which agent should handle the message"""
        context = self._get_conversation_context(message)
        
        routing_prompt = f"""
        Given the following context and user message, determine if it requires web search or not.
        
        {context}
        
        Reply with either 'web_search' or 'general' only.
        Consider:
        1. If the message contains a URL or asks about web content -> 'web_search'
        2. If the message refers to previously discussed URLs -> 'web_search'
        3. If the message is a follow-up question about previously fetched web content -> 'web_search'
        4. Otherwise -> 'general'
        """
        
        response = await self.llm.apredict(routing_prompt)
        return response.strip().lower()

    async def process_message(self, message: str, file_content: Optional[str] = None) -> Dict[str, str]:
        """Process incoming messages and route to appropriate agents"""
        try:
            # Add user message to state
            self.state.messages.append(Message(
                content=message,
                type="text",
                role="user",
                metadata={"has_file": bool(file_content)}
            ))
            
            # Add file content to context if present
            if file_content:
                self.state.context["file_content"] = file_content

            # Get conversation context
            context = self._get_conversation_context(message)
            
            # If message appears to reference previous context but we have none
            if any(word in message.lower() for word in ["you", "previous", "before", "earlier", "mentioned"]) and not context:
                return {
                    "response": "I don't have any previous context about that. Could you please provide more details or rephrase your question?",
                    "agent": None,
                    "conversation_id": id(self.state)
                }

            # Determine routing
            route = await self._route_message(message)
            logger.info(f"Message routed to: {route}")

            # Process based on routing decision
            if route == "web_search":
                self.state.current_agent = "web_search"
                # Pass context to web agent only if we have valid context
                response = await self.web_agent.process(
                    message,
                    conversation_context=context if context else None
                )
            else:
                # Default to general LLM response
                if context:
                    llm_prompt = f"""
                    {context}
                    Please provide a response considering the conversation history above.
                    Be sure to reference relevant information from previous messages if applicable.
                    """
                else:
                    llm_prompt = message
                    
                response = await self.llm.apredict(llm_prompt)

            # Store assistant response in state
            self.state.messages.append(Message(
                content=response,
                type="text",
                role="assistant",
                metadata={"agent": self.state.current_agent}
            ))
            
            return {
                "response": response,
                "agent": self.state.current_agent,
                "conversation_id": id(self.state)
            }

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return {"error": f"Error processing message: {str(e)}"}

    async def get_state(self) -> Dict[str, Any]:
        """Return current supervisor state"""
        return self.state.dict()

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get formatted conversation history"""
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.metadata
            }
            for msg in self.state.messages
        ]

    async def reset_state(self):
        """Reset supervisor state"""
        self.state = SupervisorState()
        self.web_agent = WebSearchAgent()  # Create new web agent instance
        logger.info("Supervisor state fully reset")