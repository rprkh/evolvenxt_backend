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
    chart_type: Optional[Literal["line", "bar", "pie"]] = None
    agent_name: Optional[str] = None
    upline_manager: Optional[str] = None
    agent_scope: Optional[Literal["ALL", "SPECIFIC"]] = None
    upline_scope: Optional[Literal["ALL", "SPECIFIC"]] = None


def get_intent_ds2(user_input: str) -> UserIntentDS2:

    prompt = f"""
        You are an intent classifier.

        Analyze the user request:
        "{user_input}"

        IMPORTANT PRIORITY RULE (MUST FOLLOW):
        - If the request includes ANY intent to visualize data (chart, graph, plot, bar, line, pie, visualize, show as, display as),
        you MUST classify it as GENERATE_CHART — even if they are asking for commissions, numbers, or specific people.

        Categorize the request into EXACTLY ONE of the following:

        1) GENERATE_CHART
        Use this if the user asks to show, display, create, generate, visualize, or plot data.
        This ALWAYS takes priority over QUERY_DATA.

        Determine chart_type:
        - "line": trends over time (months, years, dates)
        - "bar": comparisons between categories or discrete time ranges
        - "pie": proportions, percentages, distributions

        2) QUERY_DATA
        Use this ONLY if NO visualization is requested.

        Sub-categories:
        - AGENT_COMMISSIONS:
            When asking for commission data of an agent (not manager/upline) without charts.
        - GENERAL:
            Manager, upline manager, or any other non-chart data queries.

        3) GENERAL_CHAT
        Greetings, small talk, or unrelated questions.

        KEYWORD RULE (HARD CONSTRAINT):
        If the request contains ANY of the following words:
        ["chart", "graph", "plot", "bar", "line", "pie", "visualize", "visualisation", "show as", "display as"]
        → intent MUST be GENERATE_CHART.

        Examples:
        - "show the commissions for Avery Rodriguez from Jan 2022 to Feb 2022 as a bar graph"
        → intent: GENERATE_CHART, chart_type: "bar"

        - "display agent commissions over time"
        → intent: GENERATE_CHART, chart_type: "line"

        - "what were Avery Rodriguez's commissions in Jan 2022?"
        → intent: QUERY_DATA, sub_category: AGENT_COMMISSIONS

        - "hi there"
        → intent: GENERAL_CHAT

        Return ONLY valid JSON that matches the UserIntentDS2 schema.
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
    