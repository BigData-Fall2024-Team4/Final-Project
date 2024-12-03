from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
import logging
from .web_agent import WebSearchAgent
from .canvas.post_agent import CanvasPostAgent
import re

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
    
    def __init__(self, openai_api_key: str, canvas_api_key: str = None, canvas_base_url: str = None):
        self.llm = ChatOpenAI(api_key=openai_api_key)
        self.web_agent = WebSearchAgent()
        self.canvas_agent = CanvasPostAgent(canvas_api_key, canvas_base_url) if canvas_api_key else None
        self.state = SupervisorState()
        self.pending_announcement = None  # Store pending announcement content
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
        routing_prompt = f"""
        Given the following message, determine if it requires:
        1. web_search - If it contains a URL or asks for web content
        2. canvas_post - If it mentions posting to Canvas or course announcements
        3. canvas_list - If it asks about available courses or course listing
        4. general - For general queries
        
        Message: {message}
        
        Reply with either 'web_search', 'canvas_post', 'canvas_list', or 'general' only.
        Consider:
        1. If the message asks about listing courses, available courses -> 'canvas_list'
        2. If the message contains a URL or asks about web content -> 'web_search'
        3. If the message mentions posting to Canvas -> 'canvas_post'
        4. Otherwise -> 'general'
        """
        
        response = await self.llm.apredict(routing_prompt)
        return response.strip().lower()

    def _extract_title(self, message: str) -> Optional[str]:
        """Extract title from message if specified"""
        if "title:" in message.lower():
            title_match = re.search(r'title:\s*([^\n]+)', message, re.IGNORECASE)
            if title_match:
                return title_match.group(1).strip()
        return None
        
    async def get_available_courses(self) -> List[Dict[str, Any]]:
        """Get list of available courses"""
        if not self.canvas_agent:
            return []
        return await self.canvas_agent.list_courses()
    
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

            # Check if this is a confirmation for pending announcement
            lower_message = message.lower()
            if lower_message in ['yes', 'post it', 'post', 'yes post it'] and self.pending_announcement:
                if self.canvas_agent:
                    try:
                        course_name = self.pending_announcement['course_name']
                        content = self.pending_announcement['content']
                        title = self.pending_announcement['title']
                        
                        post_result = await self.canvas_agent.process(
                            content,
                            f"title: {title}\nannouncement for [{course_name}]"
                        )
                        
                        if post_result.get('success', False):
                            response = f"Successfully posted the announcement to {course_name}!"
                        else:
                            response = f"Failed to post announcement: {post_result.get('message', 'Unknown error')}"
                            
                        # Clear pending announcement
                        self.pending_announcement = None
                            
                    except Exception as e:
                        response = f"Error posting announcement: {str(e)}"
                    
                    self.state.messages.append(Message(
                        content=response,
                        type="text",
                        role="assistant",
                        metadata={"agent": "canvas_post"}
                    ))
                    
                    return {
                        "response": response,
                        "agent": "canvas_post",
                        "conversation_id": id(self.state)
                    }
                    
            elif lower_message in ['no', 'cancel', 'dont post', "don't post"]:
                if self.pending_announcement:
                    self.pending_announcement = None
                    return {
                        "response": "Announcement cancelled.",
                        "agent": "canvas_post",
                        "conversation_id": id(self.state)
                    }

            # Regular message processing
            context = self._get_conversation_context(message)
            route = await self._route_message(message)
            logger.info(f"Message routed to: {route}")

            if route == "canvas_list":
                if not self.canvas_agent:
                    response = "Canvas is not configured. Please provide Canvas API credentials."
                else:
                    courses = await self.canvas_agent.list_courses()
                    if courses:
                        course_list = "\n".join([
                            f"• {course['name']} (Code: {course['code']})"
                            + (f" - {course['students']} students" if course['students'] else "")
                            for course in courses
                        ])
                        response = f"Available courses:\n{course_list}"
                    else:
                        response = "No courses found or error retrieving courses."
                
                self.state.current_agent = "canvas_list"

            elif route == "canvas_post":
                if not self.canvas_agent:
                    response = "Canvas posting is not configured. Please provide Canvas API credentials."
                else:
                    # Extract course name
                    course_match = re.search(r'\[(.*?)\]', message)
                    if not course_match:
                        return {
                            "response": "Please specify a course name in square brackets, e.g. [Course Name]",
                            "agent": route,
                            "conversation_id": id(self.state)
                        }
                    
                    course_name = course_match.group(1)
                    
                    # Generate content
                    content = await self.web_agent.process(
                        message.replace(f"[{course_name}]", "").strip(),
                        conversation_context=context if context else None
                    )
                    
                    # Get title from message or generate one
                    title = self._extract_title(message)
                    if not title:
                        title = await self.canvas_agent.announcement_agent.generate_title(content)
                    
                    # Store as pending announcement
                    self.pending_announcement = {
                        "course_name": course_name,
                        "content": content,
                        "title": title
                    }
                    
                    response = (
                        f"Here's the content I generated for {course_name}:\n\n"
                        f"Title: {title}\n\n"
                        f"{content}\n\n"
                        "Would you like me to post this announcement? (Reply with 'yes' to post or 'no' to cancel)"
                    )
                    
                self.state.current_agent = "canvas_post"
                
            elif route == "web_search":
                self.state.current_agent = "web_search"
                response = await self.web_agent.process(
                    message,
                    conversation_context=context if context else None
                )
                
            else:
                if context:
                    llm_prompt = (
                        f"{context}\n"
                        "Please provide a response considering the conversation history above."
                    )
                else:
                    llm_prompt = message
                    
                response = await self.llm.apredict(llm_prompt)

            # Store assistant response
            self.state.messages.append(Message(
                content=response,
                type="text",
                role="assistant",
                metadata={"agent": route}
            ))
            
            return {
                "response": response,
                "agent": route,
                "conversation_id": id(self.state)
            }

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return {
                "error": f"Error processing message: {str(e)}"
            }

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
        self.pending_announcement = None  # Clear any pending announcements
        if self.canvas_agent:
            await self.canvas_agent.close()  # Close any existing Canvas sessions
        logger.info("Supervisor state fully reset")

async def close(self):
        """Cleanup method for closing all agent sessions"""
        if hasattr(self, 'web_agent'):
            await self.web_agent.close()
        if hasattr(self, 'canvas_agent'):
            await self.canvas_agent.close()
        logger.info("All agent sessions closed")