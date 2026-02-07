import os
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass
import json
from pydantic import BaseModel
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

app = FastAPI(title="EvolveNXT AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000/" if CONFIG.ENVIRONMENT_TYPE == "development" else "https://evolvenxt-frontend.vercel.app/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


supabase: Client = create_client(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_KEY)
gemini_client = genai.Client(api_key=CONFIG.GEMINI_API_KEY)
# client = InferenceClient(model=CONFIG.HF_MODEL_ID, token=os.getenv("HUGGING_FACE_API_KEY"))

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

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

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    prompt = req.message

    result = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    print(f"User prompt: {prompt}\nGenerated response: {result.text}")

    return {"response": result.text}