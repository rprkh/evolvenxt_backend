import os
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass
from .general_helpers import get_intent_ds2, clean_sql
import json
import traceback

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

def format_data_for_line_or_bar_chart(rows):
    if not rows:
        return []

    time_columns = [
        'commission_quarter', 'commission_year', 'commission_month',
        'commission_date', 'month', 'date', 'period', 'year', 'quarter',
        'cumulative_commission', 'cumulative_commissions', 
        'total_commission', 'total_commissions', 'commission_amount'
    ]
    name_columns = [
        'agent_name', 'upline_manager', 'agency_name',
        'name', 'agent', 'manager', 'contractor', 'company', 'agency_name'
    ]
    EXCLUDE_KEYS = {'id', 'agent_id', 'upline_id'}

    time_key = next((c for c in time_columns if c in rows[0]), None)

    grouped = {}

    for idx, row in enumerate(rows):
        period = str(row.get(time_key)) if time_key else f"row_{idx}"

        if period not in grouped:
            grouped[period] = {"period": period}

        name = next((row[col] for col in name_columns if col in row and row[col]), None)

        for key, value in row.items():
            if key in EXCLUDE_KEYS or key == time_key:
                continue
            try:
                numeric_value = float(value)
            except (ValueError, TypeError):
                continue

            if name:
                grouped[period][name] = numeric_value
            else:
                grouped[period][key] = numeric_value

        # include all key-value pairs
        if len(grouped[period]) == 1:
            for key, value in row.items():
                if key in EXCLUDE_KEYS:
                    continue
                try:
                    grouped[period][key] = float(value)
                except (ValueError, TypeError):
                    grouped[period][key] = str(value)

    try:
        return sorted(grouped.values(), key=lambda x: x["period"])
    except Exception:
        return list(grouped.values())


def format_data_for_pie_chart(rows):
    if not rows:
        return []

    name_columns = ['agent_name', 'upline_manager', 'agency_name', 'name', 'salesperson', 'year']
    value_columns = [
        'commission_amount', 'commission_year', 'commission_month',
        'cumulative_commission', 'cumulative_commissions',
        'total_commission', 'total_commissions', 'bonus', 'amount', 'total_sales'
    ]

    name_key = next((col for col in name_columns if col in rows[0]), None)
    value_key = next((col for col in value_columns if col in rows[0]), None)

    if not name_key or not value_key:
        for key, value in rows[0].items():
            if not name_key and isinstance(value, str) and key not in ['id', 'agent_id', 'upline_id', 'commission_date', 'commission_quarter']:
                name_key = key
            elif not value_key and isinstance(value, (int, float)):
                value_key = key

    result = []
    for row in rows:
        try:
            if not name_key or not value_key:
                for key, value in row.items():
                    if key in ['id', 'agent_id', 'upline_id']:
                        continue
                    result.append({
                        "name": str(key),
                        "value": float(value) if isinstance(value, (int, float)) else 0
                    })
                continue

            result.append({
                "name": str(row.get(name_key, 'Unknown')),
                "value": float(row.get(value_key, 0) or 0)
            })
        except (ValueError, TypeError):
            continue

    return result

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

            number_of_rows_returned_by_sql_query = len(supabase_response.data)
            print(f"No of rows returned by the SQL query from Supabase: {number_of_rows_returned_by_sql_query}")

            if number_of_rows_returned_by_sql_query > 6:
                if isinstance(supabase_response.data, list) and len(supabase_response.data) > 0:
                    formatted_string = ""
                    
                    for item in supabase_response.data:
                        for key, value in item.items():
                            formatted_string += f"{key}: {value}\n"
                        formatted_string += "\n"
                    
                    return formatted_string.strip()
                else:
                    return "No data found."
            else:
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
        question = user_input
        chart_type = intent_data.chart_type or "line"  # Default to line

        input_to_model = f"You are a PostgreSQL expert.\n\nSchema:{table_schema}\n\nRelationships:{relationships}\n\nImportant points to consider while generating PostgreSQL queries:{important_points}\n\nQuestion:{question}\n\nReturn only the PostgreSQL query. Do not change the column names from the original table. Do not include explanations."

        print(f"DS-2 chart question: {question}")
        print(f"Chart type: {chart_type}")

        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=input_to_model,
                config={"temperature": 0.0}
            )

            clean_sql_query = clean_sql(response.text)
            print(f"DS-2 chart SQL query: {clean_sql_query}")

            supabase_response = supabase.rpc(
                "run_sql",
                {"query": clean_sql_query}
            ).execute()
            print(f"DS-2 chart data: {supabase_response.data}")

            if chart_type == "pie":
                formatted_chart_data = format_data_for_pie_chart(supabase_response.data)
            else:
                formatted_chart_data = format_data_for_line_or_bar_chart(supabase_response.data)
            
            print(f"Formatted chart data: {formatted_chart_data}")

            if supabase_response.data == None:
                return "The model was unable to generate a chart for this request from the database. Please try again."

            if not formatted_chart_data:
                return "The model was unable to generate a chart for this request. Please try again."

            chart_payload = {
                "type": "chart",
                "content": f"I've generated a {chart_type} chart based on your request.",
                "chart_data": formatted_chart_data,
                "chart_type": chart_type
            }
            return json.dumps(chart_payload)

        except:
            print(f"Chart generation error")
            
            return "Please rephrase your question to be more specific about the chart you want to generate."
    else:
        try:
            chat_session = gemini_client.chats.create(
                model="gemini-2.0-flash",
                config={"system_instruction": "Your name is DS-2. You are a PostgreSQL expert."}
            )
            general_chat_response = chat_session.send_message(user_input)

            return general_chat_response.text
        except:
            return "The model was unable to understand your request. Please try again with another prompt."
