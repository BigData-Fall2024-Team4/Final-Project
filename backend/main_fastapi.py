from fastapi import FastAPI, UploadFile, Form, File, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os
from dotenv import load_dotenv
from agents.supervisor import CanvasGPTSupervisor
from pydantic import BaseModel

# Load environment variables
load_dotenv()

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic model for JSON payload
class QueryRequest(BaseModel):
    query: str

# Initialize supervisor
supervisor = CanvasGPTSupervisor(openai_api_key=os.getenv("OPENAI_API_KEY"))

@app.post("/agent-workflow")
async def process_message(
    request: QueryRequest = Body(...),  # For JSON payload
):
    try:
        # Process message through supervisor
        result = await supervisor.process_message(
            message=request.query,
            file_content=None
        )

        return result

    except Exception as e:
        return {"error": f"Error processing request: {str(e)}"}

@app.post("/agent-workflow/form")
async def process_message_form(
    message: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    try:
        # Handle file if present
        file_content = None
        if file:
            content = await file.read()
            if file.content_type.startswith('text/'):
                file_content = content.decode()

        # Process message through supervisor
        result = await supervisor.process_message(
            message=message or "",
            file_content=file_content
        )

        return result

    except Exception as e:
        return {"error": f"Error processing request: {str(e)}"}

@app.get("/supervisor-state")
async def get_supervisor_state():
    """Endpoint to check current supervisor state"""
    return await supervisor.get_state()

@app.post("/reset-supervisor")
async def reset_supervisor():
    """Endpoint to reset supervisor state"""
    await supervisor.reset_state()
    return {"status": "success", "message": "Supervisor state reset"}
