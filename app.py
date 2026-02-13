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
from helpers.ds1 import chat_with_agent_ds1
from helpers.ds2 import chat_with_agent_ds2
from helpers.general_helpers import UserIntentDS2, get_intent_ds2, clean_sql, contains_code
from typing import Optional, List

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

query_cache = {}

class ChatResponse(BaseModel):
    response: str
    show_buttons: Optional[bool] = False
    buttons: Optional[List[str]] = None

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    dataset: Optional[str] = None   # selected agent (DS-1, DS-2, TARS)
    history: Optional[List[Message]] = None

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
    user_input = req.message.strip()
    dataset = req.dataset
    last_selection = False
    history_messages = req.history or []

    if contains_code(user_input):
        return {"response": "I'm sorry, I cannot process requests containing code snippets for security reasons."}

    if user_input in ("DS-1", "DS-2", "TARS") and dataset == user_input:
        return {"response": f"You have selected {dataset}. Please ask a question."}


    if dataset == "DS-1":
        response_text = chat_with_agent_ds1(user_input)
        return {"response": response_text or "The DS-1 agent was unable to accurately process your request. Please try rephrasing your question."}

    if dataset == "DS-2":
        if user_input.lower() in ["consolidate", "upline manager"]:
            original_query = query_cache.get("last_commission_query", "agent commissions")
            
            if user_input.lower() == "consolidate":
                modified_query = f"{original_query} and {user_input.lower()} them"
                response_text = chat_with_agent_ds2(modified_query)
                query_cache.pop("last_commission_query", None)
                return {"response": response_text or "No response from DS-2 agent."}
            
            elif user_input.lower() == "upline manager":
                query_cache["waiting_for_manager"] = True
                return {"response": "Please provide the name or ID of the upline manager."}
        
        if query_cache.get("waiting_for_manager"):
            original_query = query_cache.get("last_commission_query", "agent commissions")
            modified_query = f"{original_query} for upline manager {user_input}"
            response_text = chat_with_agent_ds2(modified_query)
            query_cache.pop("last_commission_query", None)
            query_cache.pop("waiting_for_manager", None)
            return {"response": response_text or "No response from DS-2 agent."}
        
        intent = get_intent_ds2(user_input)
        if intent.sub_intent == "AGENT_COMMISSIONS":
            query_cache["last_commission_query"] = user_input
            return {
                "response": "How would you like to view agent commissions?",
                "show_buttons": True,
                "buttons": ["Consolidate", "Upline Manager"]
            }
        
        response_text = chat_with_agent_ds2(user_input)
        return {"response": response_text or "No response from DS-2 agent."}

    if dataset not in ["DS-1", "DS-2"]:

        formatted_history = [
            {"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]}
            for m in history_messages
        ]

        print(f"User chat history with TARS: {formatted_history}")

        system_instruction = """
            Your name is TARS. You are a helpful AI assistant for general questions.
            - You can answer general queries about any topic.
            - For questions related to sales, commissions, bonuses, age, ID, tiers, orders, validity, or other dataset-specific queries, instruct the user to use the dropdown and select the appropriate dataset agent (DS-1 or DS-2).
        """

        try:
            chat_session = gemini_client.chats.create(
                model="gemini-2.0-flash",
                history=formatted_history,
                config={"system_instruction": system_instruction}
            )

            response = chat_session.send_message(user_input)
            return {"response": response.text}
        except:
            return {"response": "TARS was unable to understand your question. Please try again with another prompt or selec a specific agent from the dropdown to get information related to the datasets"}
        
