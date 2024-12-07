from .base import CanvasBaseAgent
from typing import Dict, Any, List, Optional, Union
import logging
import re
from datetime import datetime, timezone
import json
from datetime import datetime, timezone, timedelta  
import json  

logger = logging.getLogger(__name__)

class AssignmentAgent(CanvasBaseAgent):
    """Enhanced agent for managing Canvas assignments with improved parsing"""
    
    SUBMISSION_TYPES = {
        "no submission": ["none"],
        "text entry": ["online_text_entry"],
        "website url": ["online_url"],
        "file uploads": ["online_upload"],
        "media recording": ["media_recording"],
        "student annotation": ["student_annotation"],
        "external tool": ["external_tool"],
        "on paper": ["on_paper"],
        "online": ["online_text_entry", "online_url", "online_upload", "media_recording"]
    }
    
    def parse_questions(self, content: str) -> str:
        """Parse questions into HTML format for Canvas"""
        html_content = "<div class='assignment-questions'>"
        
        # Split content into questions
        questions = re.split(r'\d+\.', content)[1:]  # Skip empty first split
        
        for i, question in enumerate(questions, 1):
            html_content += f"<div class='question'><p><strong>Question {i}.</strong> "
            
            # Split into question text and options
            parts = question.strip().split('Options:', 1)
            if len(parts) == 2:
                question_text, options = parts
                html_content += f"{question_text.strip()}</p>"
                
                # Parse options
                html_content += "<ul class='options'>"
                options_list = options.strip().split('\n')
                for option in options_list:
                    if option.strip().startswith(('A.', 'B.', 'C.', 'D.')):
                        html_content += f"<li>{option.strip()}</li>"
                html_content += "</ul>"
                
                # Extract correct answer if present
                correct_match = re.search(r'\(Correct Answer:\s*([A-D])\)', question)
                if correct_match:
                    correct_answer = correct_match.group(1)
                    html_content += f"<p class='correct-answer'><em>Correct Answer: {correct_answer}</em></p>"
            else:
                html_content += f"{question.strip()}</p>"
            
            html_content += "</div>"
        
        html_content += "</div>"
        return html_content

    def parse_submission_types(self, query: str) -> List[str]:
        """Extract submission types from query"""
        submission_types = []
        query_lower = query.lower()
        
        # Check for specific submission type mentions
        for key, values in self.SUBMISSION_TYPES.items():
            if key in query_lower:
                submission_types.extend(values)
                
        # Default to online text entry if no specific type mentioned
        if not submission_types:
            submission_types = ["online_text_entry"]
            
        return list(set(submission_types))

    def parse_points(self, query: str) -> int:
        """Extract points from query"""
        points_match = re.search(r'points?\s*(?:should\s*be\s*)?(\d+)', query.lower())
        return int(points_match.group(1)) if points_match else 100

    def parse_due_date(self, query: str) -> Optional[str]:
        """Extract due date from query and convert to Canvas-compatible ISO 8601 format"""
        try:
            # First look for the date pattern
            date_patterns = [
                # Match format like "12/7/2024 10:00 PM"
                r'due\s*(?:date|on|by)?\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))',
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, query, re.IGNORECASE)
                if match:
                    date_str = match.group(1).strip()
                    try:
                        # Parse the datetime
                        dt = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
                        
                        # Convert to user's timezone (assuming UTC for now, you might want to make this configurable)
                        local_tz = timezone.utc
                        dt = dt.replace(tzinfo=local_tz)
                        
                        # Format in Canvas's expected format (ISO 8601 with timezone)
                        # Example: 2024-12-07T22:00:00Z
                        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                        
                    except ValueError as e:
                        logger.error(f"Error parsing date '{date_str}': {str(e)}")
                        return None
            
            logger.info("No valid date pattern found in query")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing date: {str(e)}")
            return None



    async def create_assignment(self, course_id: str, name: str, description: str,
                          points: int = 100, due_date: Optional[str] = None, 
                          submission_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a course assignment with enhanced parsing"""
        try:
            await self._ensure_session()
            
            payload = {
                'assignment': {
                    'name': name,
                    'description': description,
                    'points_possible': points,
                    'submission_types': submission_types or ["online_text_entry"],
                    'published': False,
                    'notify_of_update': False,
                }
            }
            
            if due_date:
                # Only set the due date, without automatic unlock/lock dates
                payload['assignment']['due_at'] = due_date
            
            logger.info(f"Creating assignment with payload: {json.dumps(payload, indent=2)}")
            
            async with self.session.post(
                f"{self.base_url}/api/v1/courses/{course_id}/assignments",
                headers=self.headers,
                json=payload
            ) as response:
                response_text = await response.text()
                if response.status not in (200, 201):
                    logger.error(f"Error creating assignment: {response_text}")
                    return {"error": f"API Error: {response_text}"}
                return json.loads(response_text)
        except Exception as e:
            logger.error(f"Error creating assignment: {str(e)}")
            return {"error": str(e)}




    async def process_assignment_query(self, query: str, course_id: str) -> Dict[str, Any]:
        """Process an assignment creation query"""
        try:
            # Extract title/name
            name = "Assignment"  # default name
            title_match = re.search(r'title:\s*([^\n]+)', query)
            if title_match:
                name = title_match.group(1).strip()
            
            # Extract description - everything after the course specification
            course_match = re.search(r'\[(.*?)\]', query)
            if not course_match:
                return {"error": "No course specified"}
            
            description = query[query.find(']') + 1:].strip()
            if title_match:
                description = description.replace(title_match.group(0), '').strip()
            
            # Parse other parameters
            points = self.parse_points(query)
            due_date = self.parse_due_date(query)
            submission_types = self.parse_submission_types(query)
            
            # Create the assignment
            return await self.create_assignment(
                course_id=course_id,
                name=name,
                description=description,
                points=points,
                due_date=due_date,
                submission_types=submission_types
            )
            
        except Exception as e:
            logger.error(f"Error processing assignment query: {str(e)}")
            return {"error": str(e)}