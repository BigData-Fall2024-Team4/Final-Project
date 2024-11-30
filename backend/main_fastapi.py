from fastapi import FastAPI, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import uvicorn
from typing import Optional
import os
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your Chrome extension's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.post("/agent-workflow")
async def process_message(
    message: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    try:
        # Initialize conversation with system message
        messages = [
            {"role": "system", "content": "You are a helpful assistant who processes user queries and files."}
        ]

        # Add user message if present
        if message:
            messages.append({"role": "user", "content": message})

        # Handle file if present
        if file:
            # Read file content
            content = await file.read()
            
            # Convert to text if it's a text file
            if file.content_type.startswith('text/'):
                file_content = content.decode()
                messages.append({
                    "role": "user",
                    "content": f"File content:\n{file_content}"
                })
            else:
                messages.append({
                    "role": "user",
                    "content": f"File uploaded: {file.filename} (binary file)"
                })

        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4",  # or your preferred model
            messages=messages,
            max_tokens=1000
        )

        # Extract and return the response
        ai_response = response.choices[0].message.content

        return {"response": ai_response}

    except Exception as e:
        return {"response": f"Error processing request: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)