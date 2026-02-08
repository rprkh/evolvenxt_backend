import os
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass
import json
from pydantic import BaseModel
import re
from helpers import ds1, ds2
# import torch

load_dotenv()

@dataclass
class CONFIG:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    ENVIRONMENT_TYPE = os.getenv("ENVIRONMENT_TYPE")
    # OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    # HUGGING_FACE_API_KEY = os.getenv("HUGGING_FACE_API_KEY")
    # MODEL_PATH = "flan_t5_sql"
    # DEVICE = torch.device("cpu")
    # HF_MODEL_ID = "rprkh/t5_flan"

app = FastAPI(
    title="EvolveNXT AI Agent",
    redirect_slashes=False
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000", "https://evolvenxt-frontend.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


supabase: Client = create_client(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_KEY)
gemini_client = genai.Client(api_key=CONFIG.GEMINI_API_KEY)
# client = InferenceClient(model=CONFIG.HF_MODEL_ID, token=os.getenv("HUGGING_FACE_API_KEY"))

class ChatResponse(BaseModel):
    response: str

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    history: list[Message]
    message: str

@app.get("/application_initialization")
def application_initialization():
    if not supabase or not gemini_client:
        return {"message": "Initialization failed", "success": False}
        
    return {
        "message": "Application initialized successfully",
        "supabase_connected": True,
        "gemini_client_initialized": True
    }

@app.get("/")
def health():
    return {
        "status": "ok", 
        "platform": "vercel"
    }

def contains_code(text):
    code_patterns = [r"<script.*?>", r"import\s+.*", r"def\s+\w+\(.*\):", r"SELECT\s+.*\s+FROM"]

    return any(re.search(pattern, text, re.IGNORECASE) for pattern in code_patterns)

class Intent(BaseModel):
    dataset_choice: str  # Options: "DS-1", "DS-2", or "NONE"

def get_user_intent(message: str) -> str:
    prompt = f"""
    Analyze the user's message and determine if they are selecting a dataset.
    Datasets available: DS-1 (Sales) and DS-2 (Inventory).
    
    User message: "{message}"
    
    Return JSON with the key "dataset_choice". 
    Values must be exactly "DS-1", "DS-2", or "NONE".
    """
    
    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": Intent,
        }
    )
    
    data = json.loads(response.text)

    return data.get("dataset_choice", "NONE")

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    user_input = req.message

    if contains_code(user_input):
        return {
            "response": "I'm sorry, I cannot process requests containing code snippets for security reasons."
        }

    choice = get_user_intent(user_input)

    try:
        if choice == "DS-1":
            response_text = ds1.chat_with_agent(user_input)
            return {"response": response_text or "No response from DS-1 agent."}

        elif choice == "DS-2":
            response_text = ds2.chat_with_agent(user_input)
            return {"response": response_text or "No response from DS-2 agent."}

        else:
            formatted_history = [
                {
                    "role": "user" if m.role == "user" else "model",
                    "parts": [{"text": m.content}]
                }
                for m in req.history or []
            ]
            chat_session = gemini_client.chats.create(
                model="gemini-2.0-flash",
                history=formatted_history,
                config={
                    "system_instruction": (
                        "Your name is TARS. You are a helpful AI assistant. "
                        "Answer the user's questions based on the conversation history "
                        "and provide accurate and concise responses."
                    )
                }
            )

            response = chat_session.send_message(user_input)
            return {"response": response.text}

    except Exception as e:
        print(f"Error in chat: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while processing chat"
        )