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
from typing import Literal
import re
from .general_helpers import get_intent, clean_sql

load_dotenv()

@dataclass
class CONFIG:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    ENVIRONMENT_TYPE = os.getenv("ENVIRONMENT_TYPE")

supabase: Client = create_client(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_KEY)
gemini_client = genai.Client(api_key=CONFIG.GEMINI_API_KEY)


def pivot_data(rows):
    if not rows:
        return []

    pivoted = {}

    EXCLUDE_KEYS = {"year", "name", "id"}

    for row in rows:
        year = str(row.get("year"))
        name = row.get("name")

        if year not in pivoted:
            pivoted[year] = {"year": year}

        for key, value in row.items():
            if key in EXCLUDE_KEYS:
                continue

            if name:
                pivoted[year][f"{name}_{key}"] = float(value or 0)
            else:
                pivoted[year][key] = float(value or 0)

    return sorted(pivoted.values(), key=lambda x: x["year"])


table_schema = """
Table bonus_pay(id, year, bonus, tier)
Table orders(id, order_date, salesperson_id, amount, validity: "valid" or "invalid")
Table salesperson(id, name, age)
Table salesperson_data(id, name, age, sales_in_2012, bonus_2012, sales_in_2013, bonus_2013, sales_in_2014, bonus_2014, sales_in_2015, bonus_2015)
Table training(id, salesperson_id, start_date, end_date)
"""

relationships = """
orders.salesperson_id = salesperson.id
orders.salesperson_id = salesperson_data.id
training.salesperson_id = salesperson.id
training.salesperson_id = salesperson_data.id
orders.salesperson_id = training.salesperson_id
"""

important_points = """
A sale is only valid if it was made by a salesperson during a training window. 
The tables only contain the first name of the agent or salesperson, so you can disregard if salesperson or agent is mentioned in the question. 
For names only consider the first name. The validity in the orders columns can be either 'valid' or 'invalid'.
Most of the questions regarding sales and bonuses can be answered by writing PostgreSQL queries for the salesperson_data table.
"""

def chat_with_agent_ds1(user_input):
    question = user_input

    intent_data = get_intent(question)     

    if intent_data.intent == "QUERY_DATA":
        try:
            input_to_model = f"You are a PostgreSQL expert.\n\nSchema:{table_schema}\n\nRelationships:{relationships}\n\nImportant points to consider while generating PostgreSQL queries:{important_points}\n\nQuestion:{question}\n\nReturn only the PostgreSQL query. Do not include explanations."
            print(f"Use question: {question}")
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{input_to_model}",
                config={
                    "temperature": 0.0
                }
            )
            print(f"Response from Gemini API: {response.text}")
            clean_sql_query = clean_sql(response.text)

            supabase_response = supabase.rpc(
                "run_sql",
                {"query": clean_sql_query}
            ).execute()
            print(supabase_response.data)

            final_response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Question:{question}\n\nSQL Query:{clean_sql_query}\n\nResult from the SQL query execution:{supabase_response.data}\n\nGenerate a concise and clear answer to the question based on the SQL query result. If the question cannot be answered based on the result, say 'The data does not provide an answer to this question.'",
                config={
                    "temperature": 0.0
                }
            )

            return final_response.text
        except:
            return "TODO: I have to implement a RAG pipeline as a fallback option - Rahil"
    elif intent_data.intent == "GENERATE_CHART":
        try:
            input_to_model = f"You are a PostgreSQL expert.\n\nSchema:{table_schema}\n\nRelationships:{relationships}\n\nImportant points to consider while generating PostgreSQL queries:{important_points}\n\nQuestion:{question}\n\nReturn only the PostgreSQL query. Do not include explanations."
            print(f"Use question: {question}")
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{input_to_model}",
                config={
                    "temperature": 0.0
                }
            )
            print(f"Response from Gemini API: {response.text}")
            clean_sql_query = clean_sql(response.text)

            supabase_response = supabase.rpc(
                "run_sql",
                {"query": clean_sql_query}
            ).execute()
            print(supabase_response.data)

            formatted_chart_data = pivot_data(supabase_response.data)
            print(formatted_chart_data)

            chart_payload = {
                "type": "chart",
                "content": f"I've generated a performance chart based on your request.",
                "chart_data": formatted_chart_data,
                "chart_type": "line"
            }
            return json.dumps(chart_payload)
        except Exception as e:
            print("Please rephrase your question to be more specific about the chart you want to generate")
            
    else:
        chat_session = gemini_client.chats.create(
            model="gemini-2.0-flash",
            config={"system_instruction": "Your name is DS-1. You are a PostgreSQL expert."}
        )
        general_chat_response = chat_session.send_message(user_input)

        return general_chat_response.text
        