import os
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass
import json
from pydantic import BaseModel
import traceback
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


def format_data_for_line_or_bar_chart(rows, chart_type="line"):
    if not rows:
        return []

    EXCLUDE_KEYS = {'id', 'agent_id', 'upline_id'}

    time_columns = [
        'commission_quarter', 'commission_year', 'commission_month',
        'commission_date', 'month', 'date', 'period', 'year', 'quarter', 'sales_year',
        'bonus_year'
    ]
    name_columns = [
        'agent_name', 'upline_manager', 'agency_name',
        'name', 'agent', 'manager', 'contractor', 'company',
        'salesperson_name'
    ]

    time_key = next((c for c in time_columns if c in rows[0]), None)
    name_key = next((c for c in name_columns if c in rows[0]), None)


    if chart_type == "bar":
        result = []

        numeric_keys = [
            k for k, v in rows[0].items()
            if k not in EXCLUDE_KEYS and isinstance(v, (int, float))
        ]

        # Fallback: no numeric column detected
        if not numeric_keys:
            return []

        value_key = numeric_keys[0]

        for row in rows:
            label = (
                row.get(name_key)
                or row.get(time_key)
                or next((str(v) for v in row.values() if isinstance(v, str)), "Item")
            )

            result.append({
                "name": str(label),
                "value": float(row.get(value_key, 0) or 0)
            })

        return result

    # line chart
    grouped = {}
    valid_time_key = time_key is not None

    for idx, row in enumerate(rows):
        # Fallback period index if no time column
        period = (
            str(row.get(time_key))
            if valid_time_key
            else str(idx)
        )

        if period not in grouped:
            grouped[period] = {"period": period}

        series_name = row.get(name_key)

        numeric_found = False

        for key, value in row.items():
            if key in EXCLUDE_KEYS:
                continue

            try:
                numeric_value = float(value)
                numeric_found = True

                # Prefer named series, else use key
                series_label = (
                    str(series_name)
                    if series_name
                    else key
                )

                grouped[period][series_label] = numeric_value
            except (ValueError, TypeError):
                continue

        # Ultimate fallback: plot entire row as key-value
        if not numeric_found:
            for key, value in row.items():
                try:
                    grouped[period][key] = float(value)
                except (ValueError, TypeError):
                    continue

    return sorted(grouped.values(), key=lambda x: x["period"])



def format_data_for_pie_chart(rows):
    if not rows:
        return []

    EXCLUDE_KEYS = {'id', 'agent_id', 'upline_id'}

    name_columns = ["name", "salesperson", "sales_year", "year", "order_year", "validity"]
    value_columns = ["total_valid_sales", "bonus", "total_sales", "amount", "bonus_amount", "order_count"]

    name_key = next((c for c in name_columns if c in rows[0]), None)
    value_key = next((c for c in value_columns if c in rows[0]), None)

    result = []

    # Normal (name + value detected)
    if name_key and value_key:
        for row in rows:
            result.append({
                "name": str(row.get(name_key, "Unknown")),
                "value": float(row.get(value_key, 0) or 0)
            })
        return result

    # Fallback path 1: one row, many numeric columns
    if len(rows) == 1:
        row = rows[0]
        for key, value in row.items():
            if key in EXCLUDE_KEYS:
                continue
            try:
                result.append({
                    "name": key,
                    "value": float(value)
                })
            except (ValueError, TypeError):
                continue

        return result

    # Fallback path 2: multiple rows, no clear schema
    for idx, row in enumerate(rows):
        label = (
            row.get(name_key)
            or row.get("name")
            or row.get("salesperson")
            or f"Item {idx + 1}"
        )

        numeric_value = None
        for key, value in row.items():
            if key in EXCLUDE_KEYS:
                continue
            try:
                numeric_value = float(value)
                break
            except (ValueError, TypeError):
                continue

        if numeric_value is not None:
            result.append({
                "name": str(label),
                "value": numeric_value
            })

    return result




table_schema = """
Table bonus_pay(id, year, bonus, tier)
Table orders(id, order_date, salesperson_id, amount, validity: "valid" or "invalid")
Table salesperson(id, name, age)
Table training(id, salesperson_id, start_date, end_date)
"""

relationships = """
orders.salesperson_id = salesperson.id
training.salesperson_id = salesperson.id
orders.salesperson_id = training.salesperson_id
"""

important_points = """
The tables only contain the first name of the agent or salesperson, so you can disregard if salesperson or agent is mentioned in the question. 
For names only consider the first name. The validity in the orders columns can be either 'valid' or 'invalid'.
For questions related to bonuses, first compute the valid sales then use this to determine which tier it belongs to. Use the correct tier to look up the bonus amount.
BONUS EDGE CASES:
- If a salesperson has no valid sales for a given year, the bonus is 0.
- If computed valid sales do not qualify for any tier in bonus_pay, return a bonus of 0.
- Bonus queries MUST return a row for the requested year, even if the bonus is 0.
For generating charts based on sales, consider both 'valid' and 'invalid' sales unless otherwise specified by the user
"""

def chat_with_agent_ds1(user_input):
    question = user_input

    intent_data = get_intent(question)
    print(f"User intent: {intent_data}")

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
            return "Your request was unable to be processed. Please try again with a different prompt."
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

            if supabase_response.data == None:
                return "The model was unable to generate a chart for this request from the database. Please try again."

            chart_type = intent_data.chart_type or "line"

            if chart_type == "pie":
                formatted_chart_data = format_data_for_pie_chart(supabase_response.data)
            elif chart_type == "bar":
                formatted_chart_data = format_data_for_line_or_bar_chart(supabase_response.data)
            else:
                formatted_chart_data = format_data_for_line_or_bar_chart(supabase_response.data)

            print(formatted_chart_data)

            if not formatted_chart_data:
                return "The model was unable to generate a chart for this request. Please try again."

            chart_payload = {
                "type": "chart",
                "content": f"I've generated a {chart_type} chart based on your request.",
                "chart_data": formatted_chart_data,
                "chart_type": chart_type
            }
            return json.dumps(chart_payload)
        # except Exception as error:
        except:
            # traceback.print_exc()
            return "Please rephrase your question to be more specific about the chart you want to generate."
            
    else:
        try:
            chat_session = gemini_client.chats.create(
                model="gemini-2.0-flash",
                config={"system_instruction": "Your name is DS-1. You are a PostgreSQL expert."}
            )
            general_chat_response = chat_session.send_message(user_input)

            return general_chat_response.text
        except:
            return "The model was unable to understand your request. Please try again with another prompt."
        