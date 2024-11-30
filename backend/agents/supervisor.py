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

    async def _route_message(self, message: str) -> str:
        """Determine which agent should handle the message"""
        routing_prompt = f"""
        Given the following user message, determine if it requires web search or not.
        Message: {message}
        
        Reply with either 'web_search' or 'general' only.
        """
        
        response = await self.llm.apredict(routing_prompt)
        return response.strip().lower()

    async def process_message(self, message: str, file_content: Optional[str] = None) -> Dict[str, str]:
        """Process incoming messages and route to appropriate agents"""
        try:
            # Add message to state
            self.state.messages.append(Message(content=message))
            
            # Add file content to context if present
            if file_content:
                self.state.context["file_content"] = file_content

            # Determine routing
            route = await self._route_message(message)
            logger.info(f"Message routed to: {route}")

            # Process based on routing decision
            if route == "web_search":
                self.state.current_agent = "web_search"
                response = await self.web_agent.process(message)
            else:
                # Default to general LLM response
                response = await self.llm.apredict(message)

            # Store response in state
            self.state.messages.append(Message(content=response))
            
            return {"response": response, "agent": self.state.current_agent}

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return {"error": f"Error processing message: {str(e)}"}

    async def get_state(self) -> Dict[str, Any]:
        """Return current supervisor state"""
        return self.state.dict()

    async def reset_state(self):
        """Reset supervisor state"""
        self.state = SupervisorState()
        logger.info("Supervisor state reset")