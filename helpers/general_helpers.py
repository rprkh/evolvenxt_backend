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
from typing import Literal, Optional
import re

@dataclass
class CONFIG:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    ENVIRONMENT_TYPE = os.getenv("ENVIRONMENT_TYPE")

load_dotenv()

class UserIntent(BaseModel):
    intent: Literal["QUERY_DATA", "GENERATE_CHART", "GENERAL_CHAT"]

def get_intent(user_input):
    prompt = f"""
    Analyze the user request: "{user_input}"
    
    Categorize it:
    - GENERATE_CHART: If they ask you to show, display, portray, create or generate a chart, plot, graph or visualization.
    - QUERY_DATA: If they want a specific numbers, list, information or data.
    - GENERAL_CHAT: Greeting or off-topic.
    """
    
    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": UserIntent,
        }
    )
    return UserIntent.model_validate_json(response.text)

def clean_sql(text: str) -> str:
    text = re.sub(r"```sql\s*|```", "", text, flags=re.IGNORECASE)
    text = re.sub(r";\s*$", "", text)

    return text.strip()

gemini_client = genai.Client(api_key=CONFIG.GEMINI_API_KEY)


class UserIntentDS2(BaseModel):
    intent: Literal["QUERY_DATA", "GENERATE_CHART", "GENERAL_CHAT"]
    sub_intent: Optional[Literal["AGENT_COMMISSIONS", "GENERAL"]] = None
    agent_name: Optional[str] = None
    upline_manager: Optional[str] = None
    agent_scope: Optional[Literal["ALL", "SPECIFIC"]] = None
    upline_scope: Optional[Literal["ALL", "SPECIFIC"]] = None


def get_intent_ds2(user_input: str) -> UserIntentDS2:
    """
    Calls Gemini to classify user intent for DS-2.
    """
    prompt = f"""
    Analyze the user request: "{user_input}"
    
    Categorize it:
    - GENERATE_CHART: If they ask you to show, display, create or generate a chart, plot, graph, or visualization.
    - QUERY_DATA: If they want specific numbers, lists, information or data. This has 2 sub-categories:
        - AGENT_COMMISSIONS: If they want information about the commission of an agent
        - GENERAL: Any other data query
    - GENERAL_CHAT: Greeting or off-topic.
    
    Return JSON matching the schema of UserIntentDS2.
    """
    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": UserIntentDS2,
        }
    )
    return UserIntentDS2.model_validate_json(response.text)

    