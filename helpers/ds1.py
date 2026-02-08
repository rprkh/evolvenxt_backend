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

def chat_with_agent(user_input):
    question = user_input
    input_to_model = f"You are a SQL expert.\n\nSchema:{table_schema}\n\nRelationships:{relationships}\n\nQuestion:{question}\n\nReturn only the SQL query. Do not include explanations."
    print(f"Use question: {question}")
    response = gemini_client.models.generate_content(
		model="gemini-2.5-flash",
		contents=f"{input_to_model}",
	)
    print(f"Response from Gemini API: {response.text}")

    return response.text