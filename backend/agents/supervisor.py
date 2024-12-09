from typing import Dict, Any, Optional, List, Union 
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
import logging
from .web_agent import WebSearchAgent
from .canvas.post_agent import CanvasPostAgent
import re
from datetime import datetime, timezone, timedelta  
import json  
from .document_handler import DocumentHandlerAgent

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
        self.document_handler = DocumentHandlerAgent()

        self.pending_quiz = None  
        self.pending_announcement = None 
        self.pending_assignment = None  
        self.pending_page = None  
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
        # First check explicitly for file upload before using GPT
        if "with the file uploaded" in message.lower():
            logger.info("File upload detected, routing to document handler")
            message_lower = message.lower()
            
            # Set post type based on message content
            if 'to my announcement' in message_lower or 'to my announcment' in message_lower:
                self.state.context['post_type'] = 'announcement'
            elif 'as a page' in message_lower:
                self.state.context['post_type'] = 'page'
            elif 'as an assignment' in message_lower:
                self.state.context['post_type'] = 'assignment'
            elif 'as a quiz' in message_lower:
                self.state.context['post_type'] = 'quiz'
            else:
                # Default to announcement if not specified
                self.state.context['post_type'] = 'announcement'
                
            # Extract text content if present
            if "Text:" in message:
                text_match = re.search(r'Text:\s*"([^"]+)"', message)
                if text_match:
                    self.state.context["announcement_text"] = text_match.group(1)
                    
            logger.info(f"Document handler route detected. Post type: {self.state.context.get('post_type')}")
            return "document_handler"
            
        # For non-file messages, use the GPT routing
        routing_prompt = f"""
        Given the following message, determine if it requires:
        1. canvas_page - If it contains 'as a page', 'create page', or any reference to pages
        2. canvas_assignment - If it mentions creating or generating an assignment
        3. canvas_quiz - If it mentions creating or generating a quiz
        4. canvas_list - If it asks about available courses or course listing
        5. web_search - If it contains a URL or asks for web content
        6. canvas_post - If it mentions posting to Canvas or course announcements
        7. general - For general queries

        Message: {message}

        Reply with either 'canvas_page', 'canvas_assignment', 'canvas_quiz', 'canvas_list', 'web_search', 'canvas_post', or 'general' only.
        Consider these in order:
        1. If the message contains 'as a page' or mentions pages -> 'canvas_page'
        2. If the message contains 'create an assignment' -> 'canvas_assignment'
        3. If the message mentions creating a quiz -> 'canvas_quiz'
        4. If the message asks about listing courses -> 'canvas_list'
        5. If the message contains a URL -> 'web_search'
        6. If the message mentions posting to Canvas -> 'canvas_post'
        7. Otherwise -> 'general'
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


    async def process_message(self, message: str, file_content: Optional[Dict] = None) -> Dict[str, str]:
        """Process incoming messages and route to appropriate agents"""
        try:
            # Add user message to state
            self.state.messages.append(Message(
                content=message,
                type="text",
                role="user",
                metadata={"has_file": bool(file_content)}
            ))

            # Process file if present
            if file_content:
                file_result = await self.document_handler.process_file(
                    file_content["file"],
                    file_content["filename"]
                )
                
                if not file_result["success"]:
                    return {
                        "response": f"Error processing file: {file_result.get('error', 'Unknown error')}",
                        "agent": "document_handler",
                        "conversation_id": id(self.state)
                    }
                
                # Add file content to message metadata
                self.state.messages[-1].metadata.update({
                    "file_content": file_result["content"],
                    "file_type": file_result["file_type"],
                    "filename": file_result["filename"]
                })

            # Handle confirmations first
            lower_message = message.lower()
            if lower_message in ['yes', 'post it', 'post', 'yes post it']:
                if self.pending_quiz:
                    return await self._handle_quiz_confirmation()
                elif self.pending_announcement:
                    return await self._handle_announcement_confirmation()
                elif self.pending_assignment:
                    return await self._handle_assignment_confirmation()
                elif self.pending_page:
                    return await self._handle_page_confirmation()

            # Handle cancellations
            elif lower_message in ['no', 'cancel', 'dont post', "don't post"]:
                return self._handle_cancellation()

            # Route the message
            route = await self._route_message(message)
            logger.info(f"Message routed to: {route}")

            # Get text content if specified (moved before routing handlers)
            text = self.state.context.get('announcement_text', 'File uploaded')

            # Handle different routes
            if route == "document_handler":
                # Get the post type from context
                post_type = self.state.context.get('post_type', 'announcement')
                
                if not file_content:
                    return {
                        "response": "No file was uploaded. Please upload a file and try again.",
                        "agent": "document_handler",
                        "conversation_id": id(self.state)
                    }

                # Create combined content with file and text
                combined_content = {
                    "text": text,
                    "file_content": file_result["content"],
                    "filename": file_result["filename"],
                    "file_type": file_result["file_type"]
                }

                # Route to appropriate handler based on post_type
                if post_type == 'announcement':
                    response = await self._handle_post_request(message, combined_content)
                elif post_type == 'page':
                    response = await self._handle_page_request(message, combined_content)
                elif post_type == 'assignment':
                    response = await self._handle_assignment_request(message, combined_content)
                elif post_type == 'quiz':
                    response = await self._handle_quiz_request(message, combined_content)
            else:
                # Get conversation context for non-document routes
                context = self._get_conversation_context(message)
                
                # Handle other routes
                if route == "canvas_quiz":
                    response = await self._handle_quiz_request(message, context)
                elif route == "canvas_post":
                    response = await self._handle_post_request(message, context)
                elif route == "canvas_list":
                    response = await self._handle_list_request()
                elif route == "canvas_assignment":
                    response = await self._handle_assignment_request(message, context)
                elif route == "canvas_page":
                    response = await self._handle_page_request(message, context)
                elif route == "web_search":
                    response = await self._handle_web_search(message, context)
                else:
                    response = await self._handle_general_request(message, context)

            # Store assistant response
            self.state.messages.append(Message(
                content=response["response"],
                type="text",
                role="assistant",
                metadata={"agent": route}
            ))
            
            return response

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return {
                "error": f"Error processing message: {str(e)}",
                "response": f"Error processing message: {str(e)}",
                "agent": "error",
                "conversation_id": id(self.state)
            }


    async def _handle_page_confirmation(self) -> Dict[str, str]:
        """Handle confirmation for page creation"""
        if not self.canvas_agent:
            return {
                "response": "Canvas is not configured. Please provide Canvas API credentials.",
                "agent": "canvas_page",
                "conversation_id": id(self.state)
            }

        try:
            result = await self.canvas_agent.process(
                self.pending_page['content'],
                f"page for [{self.pending_page['course_name']}] title: {self.pending_page['title']}"
            )
            
            if result.get('success', False):
                response = f"Successfully created page in {self.pending_page['course_name']}!"
            else:
                response = f"Failed to create page: {result.get('message', 'Unknown error')}"
            
            self.pending_page = None  # Clear pending page
            
            return {
                "response": response,
                "agent": "canvas_page",
                "conversation_id": id(self.state)
            }
            
        except Exception as e:
            logger.error(f"Error creating page: {str(e)}")
            return {
                "response": f"Error creating page: {str(e)}",
                "agent": "canvas_page",
                "conversation_id": id(self.state)
            }



    async def _handle_post_request(self, message: str, content: Union[str, Dict]) -> Dict[str, str]:
        """Handle announcement posting requests"""
        if not self.canvas_agent:
            return {
                "response": "Canvas is not configured. Please provide Canvas API credentials.",
                "agent": "canvas_post",
                "conversation_id": id(self.state)
            }

        course_match = re.search(r'\[(.*?)\]', message)
        if not course_match:
            return {
                "response": "Please specify a course name in square brackets, e.g. [Course Name]",
                "agent": "canvas_post",
                "conversation_id": id(self.state)
            }
        
        course_name = course_match.group(1)
        title = self._extract_title(message)
        
        if not title:
            title = await self.canvas_agent.announcement_agent.generate_title(message)
        
        # Handle content based on type
        if isinstance(content, dict) and content.get("file_content"):
            # Handle file upload case
            file_content = content["file_content"]
            text = content.get("text", "File uploaded")
            self.pending_announcement = {
                "course_name": course_name,
                "content": text,
                "title": title,
                "file_content": file_content,
                "filename": content.get("filename")
            }
        else:
            # Handle regular text announcement
            text_content = content if isinstance(content, str) else str(content)
            self.pending_announcement = {
                "course_name": course_name,
                "content": text_content,
                "title": title
            }
        
        response = (
            f"Here's the announcement for {course_name}:\n\n"
            f"Title: {title}\n\n"
            f"{self.pending_announcement['content']}\n\n"
        )
        
        if "file_content" in self.pending_announcement:
            response += f"File to be uploaded: {self.pending_announcement['filename']}\n\n"
        
        response += "Would you like me to post this announcement? (Reply with 'yes' to post or 'no' to cancel)"
        
        return {
            "response": response,
            "agent": "canvas_post",
            "conversation_id": id(self.state)
        }


    async def _handle_quiz_confirmation(self) -> Dict[str, str]:
        """Handle confirmation for quiz creation"""
        if not self.canvas_agent:
            return {
                "response": "Canvas is not configured. Please provide Canvas API credentials.",
                "agent": "canvas_quiz",
                "conversation_id": id(self.state)
            }

        try:
            course_name = self.pending_quiz['course_name']
            content = self.pending_quiz['content']
            title = self.pending_quiz['title']
            
            quiz_result = await self.canvas_agent.process(
                content,
                f"title: {title}\nquiz for [{course_name}]"
            )
            
            if quiz_result.get('success', False):
                response = f"Successfully created quiz in {course_name}!"
            else:
                response = f"Failed to create quiz: {quiz_result.get('message', 'Unknown error')}"
                
            self.pending_quiz = None
                
        except Exception as e:
            response = f"Error creating quiz: {str(e)}"
        
        return {
            "response": response,
            "agent": "canvas_quiz",
            "conversation_id": id(self.state)
        }


    async def _handle_announcement_confirmation(self) -> Dict[str, str]:
        """Handle confirmation for announcement posting"""
        if not self.canvas_agent:
            return {
                "response": "Canvas is not configured. Please provide Canvas API credentials.",
                "agent": "canvas_post",
                "conversation_id": id(self.state)
            }

        try:
            course_name = self.pending_announcement['course_name']
            content = self.pending_announcement['content']
            title = self.pending_announcement['title']
            
            # Get file content if present
            file_content = self.pending_announcement.get('file_content')
            file_name = self.pending_announcement.get('filename')  # This needs to be changed to 'file_name'
            
            if file_content and file_name:
                # Create dictionary format for content
                content = {
                    'text': content,
                    'file_content': file_content,
                    'filename': file_name  # Match the parameter name expected by process method
                }

            # Process the announcement
            result = await self.canvas_agent.process(
                content=content,
                message=f"title: {title}\nannouncement for [{course_name}]"
            )
            
            if result.get('success', False):
                response = "Successfully posted announcement"
                if file_content:
                    response += " with file attachment"
                response += f" to {course_name}!"
            else:
                response = f"Failed to post announcement: {result.get('message', 'Unknown error')}"
                
            self.pending_announcement = None
            
            return {
                "response": response,
                "agent": "canvas_post",
                "conversation_id": id(self.state)
            }
                
        except Exception as e:
            logger.error(f"Error posting announcement: {str(e)}")
            return {
                "response": f"Error posting announcement: {str(e)}",
                "agent": "canvas_post",
                "conversation_id": id(self.state)
            }



    async def _handle_assignment_confirmation(self) -> Dict[str, str]:
        """Handle confirmation for assignment creation"""
        if not self.canvas_agent:
            return {
                "response": "Canvas is not configured. Please provide Canvas API credentials.",
                "agent": "canvas_assignment",
                "conversation_id": id(self.state)
            }

        try:
            course_id = await self.canvas_agent.get_course_id(self.pending_assignment['course_name'])
            if not course_id:
                return {
                    "response": f"Could not find course: {self.pending_assignment['course_name']}",
                    "agent": "canvas_assignment",
                    "conversation_id": id(self.state)
                }
            
            # Format due date without automatic unlock/lock dates
            due_date = self.pending_assignment['due_date']
            
            assignment_data = {
                "course_id": course_id,
                "name": self.pending_assignment['title'],
                "description": self.pending_assignment['content'],
                "points": self.pending_assignment['points'],
                "due_date": due_date,
                "submission_types": self.pending_assignment['submission_types']
            }

            # Log the assignment data for debugging
            logger.info(f"Creating assignment with data: {json.dumps(assignment_data, indent=2)}")
            
            result = await self.canvas_agent.assignment_agent.create_assignment(
                course_id=course_id,
                name=self.pending_assignment['title'],
                description=self.pending_assignment['content'],
                points=self.pending_assignment['points'],
                due_date=due_date,
                submission_types=self.pending_assignment['submission_types']
            )
            
            if 'error' in result:
                response = f"Failed to create assignment: {result['error']}"
            else:
                response = f"Successfully created assignment in {self.pending_assignment['course_name']}!"
            
            self.pending_assignment = None
            
            return {
                "response": response,
                "agent": "canvas_assignment",
                "conversation_id": id(self.state),
                "success": 'error' not in response.lower()
            }
            
        except Exception as e:
            logger.error(f"Error creating assignment: {str(e)}")
            return {
                "response": f"Error creating assignment: {str(e)}",
                "agent": "canvas_assignment",
                "conversation_id": id(self.state),
                "success": False
            }
        
        

    def _handle_cancellation(self) -> Dict[str, str]:
        """Handle cancellation of pending operations"""
        if self.pending_quiz:
            self.pending_quiz = None
            return {
                "response": "Quiz creation cancelled.",
                "agent": "canvas_quiz",
                "conversation_id": id(self.state)
            }
        elif self.pending_announcement:
            self.pending_announcement = None
            return {
                "response": "Announcement cancelled.",
                "agent": "canvas_post",
                "conversation_id": id(self.state)
            }
        elif self.pending_assignment:
            self.pending_assignment = None
            return {
                "response": "Assignment creation cancelled.",
                "agent": "canvas_assignment",
                "conversation_id": id(self.state)
            }
        elif self.pending_page:  # Add this block
            self.pending_page = None
            return {
                "response": "Page creation cancelled.",
                "agent": "canvas_page",
                "conversation_id": id(self.state)
            }
        return {
            "response": "Nothing to cancel.",
            "agent": "general",
            "conversation_id": id(self.state)
        }

    async def _handle_quiz_request(self, message: str, context: str) -> Dict[str, str]:
        """Handle quiz creation requests"""
        if not self.canvas_agent:
            return {
                "response": "Canvas is not configured. Please provide Canvas API credentials.",
                "agent": "canvas_quiz",
                "conversation_id": id(self.state)
            }

        course_match = re.search(r'\[(.*?)\]', message)
        if not course_match:
            return {
                "response": "Please specify a course name in square brackets, e.g. [Course Name]",
                "agent": "canvas_quiz",
                "conversation_id": id(self.state)
            }
        
        course_name = course_match.group(1)
        title = self._extract_title(message) or "Quiz"
        
        if "Questions" in message and "(Correct Answer:" in message:
            content = message[message.find("Questions"):]
        else:
            content = await self.web_agent.process(
                message.replace(f"[{course_name}]", "").strip(),
                conversation_context=context if context else None
            )
        
        self.pending_quiz = {
            "course_name": course_name,
            "content": content,
            "title": title
        }
        
        response = (
            f"I've prepared the quiz for {course_name}:\n\n"
            f"Title: {title}\n\n"
            f"Content Summary:\n{content[:500]}...\n\n"
            "Would you like me to create this quiz? (Reply with 'yes' to create or 'no' to cancel)"
        )
        
        return {
            "response": response,
            "agent": "canvas_quiz",
            "conversation_id": id(self.state)
        }


    async def _handle_list_request(self) -> Dict[str, str]:
        """Handle course listing requests"""
        if not self.canvas_agent:
            return {
                "response": "Canvas is not configured. Please provide Canvas API credentials.",
                "agent": "canvas_list",
                "conversation_id": id(self.state)
            }

        courses = await self.get_available_courses()
        if courses:
            course_list = "\n".join([
                f"• {course['name']} (Code: {course['code']})"
                + (f" - {course['students']} students" if course.get('students') else "")
                for course in courses
            ])
            response = f"Available courses:\n{course_list}"
        else:
            response = "No courses found or error retrieving courses."
        
        return {
            "response": response,
            "agent": "canvas_list",
            "conversation_id": id(self.state)
        }

    async def _handle_assignment_request(self, message: str, context: str) -> Dict[str, str]:
        """Handle assignment creation requests"""
        if not self.canvas_agent:
            return {
                "response": "Canvas is not configured. Please provide Canvas API credentials.",
                "agent": "canvas_assignment",
                "conversation_id": id(self.state)
            }

        # Extract course name from square brackets
        course_match = re.search(r'\[(.*?)\]', message)
        if not course_match:
            return {
                "response": "Please specify a course name in square brackets, e.g. [Course Name]",
                "agent": "canvas_assignment",
                "conversation_id": id(self.state)
            }
        
        course_name = course_match.group(1)
        
        # Extract metadata with more precise patterns
        title_match = re.search(r'title:\s*([^\n]+)', message)
        points_match = re.search(r'points\s*should\s*be\s*(\d+)', message)
        submission_match = re.search(r'submission\s*type\s*should\s*be\s*(\w+(?:\s+\w+)*)', message)
        due_date_match = re.search(r'due\s*date\s*should\s*be\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM))', message, re.IGNORECASE)
        
        # Extract assignment content
        assignment_match = re.search(r'Assignment:(.*?)(?=$)', message, re.DOTALL)
        if not assignment_match:
            return {
                "response": "Please include 'Assignment:' followed by the assignment content.",
                "agent": "canvas_assignment",
                "conversation_id": id(self.state)
            }

        assignment_content = assignment_match.group(1).strip()

        # Process due date if present
        formatted_date = None
        original_due_date = None
        if due_date_match:
            try:
                due_date = due_date_match.group(1)
                # Parse the date string
                dt = datetime.strptime(due_date, "%m/%d/%Y %I:%M %p")
                # Convert to UTC and format for Canvas
                formatted_date = dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                original_due_date = due_date
                logger.info(f"Successfully parsed due date: {formatted_date}")
            except ValueError as e:
                logger.error(f"Date parsing error: {str(e)}")
                formatted_date = None
                original_due_date = None

        # Determine submission types
        submission_types = ["online_url"] if submission_match and "url" in submission_match.group(1).lower() else ["online_text_entry"]

        # Store as pending assignment
        self.pending_assignment = {
            "course_name": course_name,
            "content": assignment_content,
            "title": title_match.group(1).strip() if title_match else "Assignment",
            "points": int(points_match.group(1)) if points_match else 100,
            "due_date": formatted_date,
            "original_due_date": original_due_date,
            "submission_types": submission_types
        }

        # Log the pending assignment for debugging
        logger.info(f"Created pending assignment: {json.dumps(self.pending_assignment, indent=2)}")
        
        # Create response message
        response_parts = [
            f"I've prepared the assignment for {course_name}:\n",
            f"Title: {self.pending_assignment['title']}",
            f"Points: {self.pending_assignment['points']}",
            f"Submission Types: {', '.join(self.pending_assignment['submission_types'])}",
            f"Due Date: {self.pending_assignment['original_due_date'] or 'No due date set'}\n",
            "Would you like me to create this assignment? (Reply with 'yes' to create or 'no' to cancel)"
        ]
        
        response = "\n".join(response_parts)
        
        return {
            "response": response,
            "agent": "canvas_assignment",
            "conversation_id": id(self.state)
        }

    async def _handle_web_search(self, message: str, context: str) -> Dict[str, str]:
        """Handle web search requests"""
        response = await self.web_agent.process(
            message,
            conversation_context=context if context else None
        )
        
        return {
            "response": response,
            "agent": "web_search",
            "conversation_id": id(self.state)
        }

    async def _handle_general_request(self, message: str, context: str) -> Dict[str, str]:
        """Handle general requests using LLM"""
        if context:
            llm_prompt = (
                f"{context}\n"
                "Please provide a response considering the conversation history above."
            )
        else:
            llm_prompt = message
            
        response = await self.llm.apredict(llm_prompt)
        
        return {
            "response": response,
            "agent": "general",
            "conversation_id": id(self.state)
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
        self.pending_quiz = None  # Clear any pending quizzes
        self.pending_assignment = None  # Clear any pending assignments
        self.pending_page = None  # Clear any pending pages - Add this line
        if self.canvas_agent:
            await self.canvas_agent.close()  # Close any existing Canvas sessions
        logger.info("Supervisor state fully reset")

    async def close(self):
        """Cleanup method for closing all agent sessions"""
        if hasattr(self, 'web_agent'):
            await self.web_agent.close()
        if hasattr(self, 'canvas_agent'):
            await self.canvas_agent.close()
        if hasattr(self, 'document_handler'):
            await self.document_handler.close()
        logger.info("All agent sessions closed")          
        
        
        
        
        
        
        
        
        
        
        