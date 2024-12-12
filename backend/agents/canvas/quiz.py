from typing import Dict, Any, List, Optional
import aiohttp
import logging
import json
from pydantic import BaseModel
import re

logger = logging.getLogger(__name__)

class QuizQuestion(BaseModel):
    question_name: str
    question_text: str
    question_type: str = "multiple_choice_question"
    points_possible: float = 1.0
    answers: List[Dict[str, Any]]
    correct_comments: Optional[str] = "Correct!"
    incorrect_comments: Optional[str] = "Please review the material and try again."

class QuizAgent:
    """Agent for handling Canvas LMS quiz operations"""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.session = None
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    def parse_formatted_questions(self, content: str) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse pre-formatted quiz questions using line by line approach"""
        try:
            questions = []
            quiz_settings = {'time_limit': 30}  # Set default time limit to 30 minutes
            
            # First check for time limit in the entire content
            time_limit_match = re.search(r"Time limit:\s*(\d+)", content)
            if time_limit_match:
                quiz_settings['time_limit'] = int(time_limit_match.group(1))
                logger.info(f"Found time limit: {quiz_settings['time_limit']} minutes")

            # Split content into lines after Questions: marker
            try:
                lines = content.split("Questions:")[1].strip().split("\n")
            except IndexError:
                lines = content.strip().split("\n")  # Try without "Questions:" marker

            current_question = None
            current_options = []
            collecting_options = False
            current_points = 1  # Default points
            total_points = 0

            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue

                # Start of a new question
                if line.startswith(tuple(f"{n}." for n in range(1, 11))):
                    # Save previous question if exists
                    if current_question and current_options:
                        formatted_q = self._format_question(current_question, current_options, points=current_points)
                        if formatted_q:
                            total_points += current_points
                            questions.append(formatted_q)
                            logger.debug(f"Added question worth {current_points} points")
                    
                    current_question = line[line.find(".")+1:].strip()
                    current_options = []
                    collecting_options = False
                    current_points = 1  # Reset to default
                    i += 1
                    continue

                # Check for points specification
                if line.lower().startswith("points:"):
                    try:
                        points_text = line.split(":")[1].strip()
                        current_points = int(''.join(filter(str.isdigit, points_text)))
                        logger.debug(f"Found points for question: {current_points}")
                    except Exception as e:
                        logger.error(f"Error parsing points: {str(e)}")
                    i += 1
                    continue

                # Start collecting options
                if line == "Options:" or line.startswith("Options:"):
                    collecting_options = True
                    i += 1
                    continue

                # Parse option lines
                if collecting_options:
                    # Try to match option line in various formats
                    for letter in "ABCD":
                        if any(line.lstrip().startswith(prefix) for prefix in [
                            f"{letter}.", f"{letter} .", f"{{{letter}.", f"{letter})", f"{letter} "
                        ]):
                            text = line[line.find(".")+1:].strip() if "." in line else line[2:].strip()
                            text = text.lstrip(". ").strip()  # Remove leading dots and spaces
                            # Remove any trailing periods if they exist
                            text = text.rstrip('.')
                            current_options.append((letter, text))
                            logger.debug(f"Added option {letter}: {text}")
                            break

                # Handle correct answer and check for points
                if "(Correct Answer:" in line:
                    correct_letter = line[line.find(":")+1:line.find(")")].strip()
                    
                    # Look ahead for points on the next line
                    if i + 1 < len(lines) and "Points:" in lines[i + 1]:
                        points_line = lines[i + 1].strip()
                        try:
                            current_points = int(''.join(filter(str.isdigit, points_line)))
                            logger.debug(f"Found points after answer: {current_points}")
                            i += 1  # Skip the points line in next iteration
                        except Exception as e:
                            logger.error(f"Error parsing points after answer: {str(e)}")
                    
                    if current_question and current_options:
                        formatted_q = self._format_question(current_question, current_options, 
                                                        correct_letter, current_points)
                        if formatted_q:
                            total_points += current_points
                            questions.append(formatted_q)
                            logger.debug(f"Added question with correct answer {correct_letter}, worth {current_points} points")
                        current_question = None
                        current_options = []
                        collecting_options = False
                        current_points = 1  # Reset for next question

                i += 1

            # Handle last question if exists
            if current_question and current_options:
                formatted_q = self._format_question(current_question, current_options, points=current_points)
                if formatted_q:
                    total_points += current_points
                    questions.append(formatted_q)

            # Update quiz settings with total points
            quiz_settings['points_possible'] = total_points
            
            # Log parsing results
            logger.info(f"Parsed {len(questions)} questions, total points: {total_points}")
            
            return questions, quiz_settings

        except Exception as e:
            logger.error(f"Error parsing questions: {str(e)}")
            logger.error(f"Content: {content}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return [], {'time_limit': 30, 'points_possible': 0}  # Return default settings
    
    def _format_question(self, question_text: str, options: List[tuple], 
                        correct_letter: str = None, points: int = 1) -> Dict[str, Any]:
        """Format a question with its options for Canvas"""
        try:
            if not options:
                return None

            canvas_answers = []
            for letter, text in options:
                canvas_answers.append({
                    "text": text,
                    "weight": 100 if letter == correct_letter else 0
                })

            return {
                "question_name": question_text[:50],
                "question_text": question_text,
                "question_type": "multiple_choice_question",
                "points_possible": points,
                "answers": canvas_answers,
                "correct_comments": f"Correct! The answer is {correct_letter}." if correct_letter else "Correct!",
                "incorrect_comments": "Please review the material and try again."
            }
        except Exception as e:
            logger.error(f"Error formatting question: {str(e)}")
            return None

    async def create_quiz(
        self,
        course_id: str,
        title: str,
        description: str = "",
        quiz_type: str = "assignment",
        time_limit: Optional[int] = None,
        allowed_attempts: int = 1,
        points_possible: int = 100,
        published: bool = False
    ) -> Dict[str, Any]:
        try:
            await self._ensure_session()
            
            title = title[:80]  # Ensure title length limit

            quiz_data = {
                "quiz": {
                    "title": title,
                    "description": description,
                    "quiz_type": quiz_type,
                    "allowed_attempts": allowed_attempts,
                    "points_possible": points_possible,
                    "published": published,
                    "show_correct_answers": True,
                    "show_correct_answers_last_attempt": True,
                    "shuffle_answers": False,  # Keep options in order
                    "hide_results": None,  # Show results immediately
                    "show_correct_answers_at_end": True,
                    "one_question_at_a_time": False,  # Show all questions at once
                    "cant_go_back": False,  # Allow going back to previous questions
                    "access_code": None  # No access code required
                }
            }

            # Only include time_limit if it's not None
            if time_limit is not None:
                quiz_data["quiz"]["time_limit"] = time_limit

            async with self.session.post(
                f"{self.base_url}/api/v1/courses/{course_id}/quizzes",
                headers=self.headers,
                json=quiz_data
            ) as response:
                if response.status in [200, 201]:
                    quiz = await response.json()
                    logger.info(f"Successfully created quiz: {title}")
                    return quiz
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to create quiz. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Failed to create quiz: {error_text}"}

        except Exception as e:
            logger.error(f"Error creating quiz: {str(e)}")
            return {"error": str(e)}

    async def add_question(self, course_id: str, quiz_id: str, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a question to an existing quiz"""
        try:
            await self._ensure_session()

            # Validate and format question data
            question = QuizQuestion(**question_data)
            formatted_question = {
                "question": {
                    "question_name": question.question_name,
                    "question_text": question.question_text,
                    "question_type": question.question_type,
                    "points_possible": question.points_possible,
                    "answers": question.answers,
                    "correct_comments": question.correct_comments,
                    "incorrect_comments": question.incorrect_comments
                }
            }

            async with self.session.post(
                f"{self.base_url}/api/v1/courses/{course_id}/quizzes/{quiz_id}/questions",
                headers=self.headers,
                json=formatted_question
            ) as response:
                if response.status in [200, 201]:
                    result = await response.json()
                    logger.info(f"Successfully added question to quiz {quiz_id}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to add question. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Failed to add question: {error_text}"}

        except Exception as e:
            logger.error(f"Error adding question: {str(e)}")
            return {"error": str(e)}

    async def publish_quiz(self, course_id: str, quiz_id: str) -> Dict[str, Any]:
        """Publish a quiz"""
        try:
            await self._ensure_session()

            update_data = {
                "quiz": {
                    "published": True
                }
            }

            async with self.session.put(
                f"{self.base_url}/api/v1/courses/{course_id}/quizzes/{quiz_id}",
                headers=self.headers,
                json=update_data
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Successfully published quiz {quiz_id}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to publish quiz. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Failed to publish quiz: {error_text}"}

        except Exception as e:
            logger.error(f"Error publishing quiz: {str(e)}")
            return {"error": str(e)}

    async def create_formatted_quiz(
        self,
        course_id: str,
        title: str,
        content: str,
        description: str = "Pre-formatted quiz questions",
        publish: bool = True
    ) -> Dict[str, Any]:
        """Create a quiz from pre-formatted questions"""
        try:
            # Parse the formatted questions
            questions = self.parse_structured_quiz(content)
            
            if not questions:
                return {
                    "success": False,
                    "message": "No valid questions could be parsed from the content"
                }

            # Create the quiz
            quiz = await self.create_quiz(
                course_id=course_id,
                title=title[:80],  # Ensure title length limit
                description=description,
                points_possible=sum(q['points_possible'] for q in questions),
                time_limit=30,  # Default time limit
                published=False
            )
            
            if isinstance(quiz, dict) and quiz.get('error'):
                return {
                    "success": False,
                    "message": f"Error creating quiz: {quiz['error']}"
                }
                
            if not quiz or not isinstance(quiz, dict) or 'id' not in quiz:
                return {
                    "success": False,
                    "message": "Failed to create quiz: Invalid response from Canvas"
                }

            quiz_id = quiz['id']
            
            # Add all questions
            for question in questions:
                result = await self.add_question(course_id, quiz_id, question)
                if isinstance(result, dict) and result.get('error'):
                    logger.error(f"Error adding question: {result['error']}")

            # Publish if requested
            if publish:
                publish_result = await self.publish_quiz(course_id, quiz_id)
                if isinstance(publish_result, dict) and publish_result.get('error'):
                    logger.error(f"Error publishing quiz: {publish_result['error']}")

            return {
                "success": True,
                "message": f"Successfully created quiz with {len(questions)} questions",
                "quiz_id": quiz_id,
                "question_count": len(questions),
                "points_possible": sum(q['points_possible'] for q in questions),
                "quiz_data": quiz
            }

        except Exception as e:
            logger.error(f"Error creating formatted quiz: {str(e)}")
            return {
                "success": False,
                "message": f"Error creating formatted quiz: {str(e)}"
            }

    async def get_quiz(self, course_id: str, quiz_id: str) -> Dict[str, Any]:
        """Get quiz details"""
        try:
            await self._ensure_session()

            async with self.session.get(
                f"{self.base_url}/api/v1/courses/{course_id}/quizzes/{quiz_id}",
                headers=self.headers
            ) as response:
                if response.status == 200:
                    quiz = await response.json()
                    return quiz
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to get quiz. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Failed to get quiz: {error_text}"}

        except Exception as e:
            logger.error(f"Error getting quiz: {str(e)}")
            return {"error": str(e)}

    async def update_quiz_settings(
        self,
        course_id: str,
        quiz_id: str,
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update quiz settings"""
        try:
            await self._ensure_session()

            async with self.session.put(
                f"{self.base_url}/api/v1/courses/{course_id}/quizzes/{quiz_id}",
                headers=self.headers,
                json={"quiz": settings}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Successfully updated quiz {quiz_id} settings")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to update quiz settings. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Failed to update quiz settings: {error_text}"}

        except Exception as e:
            logger.error(f"Error updating quiz settings: {str(e)}")
            return {"error": str(e)}

    async def delete_quiz(self, course_id: str, quiz_id: str) -> Dict[str, Any]:
        """Delete a quiz"""
        try:
            await self._ensure_session()

            async with self.session.delete(
                f"{self.base_url}/api/v1/courses/{course_id}/quizzes/{quiz_id}",
                headers=self.headers
            ) as response:
                if response.status == 200:
                    logger.info(f"Successfully deleted quiz {quiz_id}")
                    return {"success": True, "message": "Quiz deleted successfully"}
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to delete quiz. Status: {response.status}, Error: {error_text}")
                    return {"error": f"Failed to delete quiz: {error_text}"}

        except Exception as e:
            logger.error(f"Error deleting quiz: {str(e)}")
            return {"error": str(e)}

    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("Quiz agent session closed")