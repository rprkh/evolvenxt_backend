import os
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass
from .general_helpers import get_intent_ds2, clean_sql

load_dotenv()

@dataclass
class CONFIG:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    ENVIRONMENT_TYPE = os.getenv("ENVIRONMENT_TYPE")

supabase: Client = create_client(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_KEY)
gemini_client = genai.Client(api_key=CONFIG.GEMINI_API_KEY)

table_schema = """
Table: fact_commissions
Columns:
 - id: int8
 - agent_id: text 
 - agent_name: text
 - upline_id: text
 - upline_manager: text 
 - agency_name: text
 - commission_date: date 
 - commission_year: int4
 - commission_month: int4
 - commission_quarter: text
 - commission_amount: numeric
"""

relationships = "Primary Key: id"

important_points = """
The fact_commissions table contains detailed information about commissions earned by agents, including their upline managers and agency affiliations.
The commission quarter column is in the form `Q{quarter}_{year}`, where quarter is between 1 and 4, and year is a four digit number from 2022 to 2024.
Generate valid PostgreSQL queries based on the fact_commissions table schema. The PostgreSQL queries should be correct and executable without any errors.
"""


def chat_with_agent_ds2(user_input: str):
    intent_data = get_intent_ds2(user_input)
    print(f"Intent data: {intent_data}")

    if intent_data.intent == "QUERY_DATA":
        question = user_input

        input_to_model = f"You are a PostgreSQL expert.\n\nSchema:{table_schema}\n\nRelationships:{relationships}\n\nImportant points to consider while generating PostgreSQL queries:{important_points}\n\nQuestion:{question}\n\nReturn only the PostgreSQL query. Do not include explanations."

        print(f"DS-2 question: {question}")

        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=input_to_model,
                config={"temperature": 0.0}
            )

            clean_sql_query = clean_sql(response.text)
            print(f"DS-2 SQL query: {clean_sql_query}")

            supabase_response = supabase.rpc(
                "run_sql",
                {"query": clean_sql_query}
            ).execute()
            print(f"Supabase response: {supabase_response.data}")

            if isinstance(supabase_response.data, list) and len(supabase_response.data) > 0:
                formatted_string = ""
                
                for item in supabase_response.data:
                    for key, value in item.items():
                        formatted_string += f"{key}: {value}\n"
                    formatted_string += "\n"
                
                return formatted_string.strip()
            else:
                return "No data found."

        except Exception as e:
            print("Error:", e)
            return {"response": "An error occurred while processing your request."}

    elif intent_data.intent == "GENERATE_CHART":
        return {"response": "Chart generation not implemented yet."}
    else:
        chat_session = gemini_client.chats.create(
            model="gemini-2.0-flash",
            config={"system_instruction": "Your name is DS-2. You are a PostgreSQL expert."}
        )
        general_chat_response = chat_session.send_message(user_input)
        return {"response": general_chat_response.text}
