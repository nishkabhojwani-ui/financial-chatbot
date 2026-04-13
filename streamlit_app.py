"""
DP World Maritime FP&A Chatbot - Streamlit Version
Easy deployment with Streamlit Cloud
"""
import streamlit as st
import sqlite3
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import requests
from difflib import get_close_matches
import re

load_dotenv()

# Configuration
DB = 'financial_data.db'

# Get API key from Streamlit Secrets (Streamlit Cloud) or environment variables
try:
    API_KEY = st.secrets["OPENROUTER_API_KEY"]
except:
    API_KEY = os.getenv('OPENROUTER_API_KEY')

st.set_page_config(page_title="Financial Intelligence Dashboard", layout="wide")

# Load categories on startup
@st.cache_resource
def load_all_categories():
    """Load all category names from database"""
    try:
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category_name FROM pl_categories ORDER BY category_name")
        categories = [row[0] for row in cursor.fetchall()]
        conn.close()
        return categories
    except:
        return []

ALL_CATEGORIES = load_all_categories()

def get_category_mapping(search_term):
    """Fuzzy match user input to actual database categories"""
    if not search_term or not ALL_CATEGORIES:
        return search_term

    search_lower = search_term.lower().strip()

    # Try exact match
    for category in ALL_CATEGORIES:
        if category.lower() == search_lower:
            return category

    # Try fuzzy match
    close_matches = get_close_matches(search_lower, [c.lower() for c in ALL_CATEGORIES], n=1, cutoff=0.6)
    if close_matches:
        for category in ALL_CATEGORIES:
            if category.lower() == close_matches[0]:
                return category

    return search_term

def fix_month_in_sql(sql):
    """Convert numeric months to text month names"""
    month_map = {
        '1': 'January', '2': 'February', '3': 'March', '4': 'April',
        '5': 'May', '6': 'June', '7': 'July', '8': 'August',
        '9': 'September', '10': 'October', '11': 'November', '12': 'December'
    }
    for num, name in month_map.items():
        sql = re.sub(rf'month\s*=\s*{num}\b', f"month = '{name}'", sql)
    return sql

def query_db(sql):
    """Execute SQL and return results"""
    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        data = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_llm_sql(question, unit):
    """Ask LLM to generate SQL"""
    if not API_KEY:
        return None

    try:
        context = f"""You are analyzing DP World Maritime Financial P&A data.

DATABASE SCHEMA (use these exact table aliases: mf=monthly_financials, v=vessels, u=units, pc=pl_categories):
- monthly_financials (mf): Contains actual, budget, last_year, and risk_factor_10 columns
  ** CRITICAL: month column stores TEXT month names ('January', 'February', ..., 'December'), NOT numbers
  ** CRITICAL: Use 'mf.month' for month comparisons, NEVER use table alias 'm'
- vessels (v): Ship vessels with names like 'Topaz Mariner', 'Ever Given', 'Topaz Resolve', etc.
- units (u): Geographic divisions - 'Africa' or 'MENA' (Middle East & North Africa)
- pl_categories (pc): Financial categories - EXACT NAMES:
{', '.join(ALL_CATEGORIES)}

COLUMNS - Use these EXACT names:
  monthly_financials (mf): vessel_id, category_id, year, month (TEXT!), actual, budget, last_year, risk_factor_10
  vessels (v): vessel_id, vessel_name, unit_id
  units (u): unit_id, unit_name
  pl_categories (pc): category_id, category_name

Generate ONLY a SQL query to answer: "{question}"
Return JUST the SQL in a code block, no explanation.

CRITICAL RULES:
1. Use exact table aliases: mf, v, u, pc (NEVER create custom aliases)
2. Always use proper JOIN...ON with foreign keys
3. Month is TEXT - use mf.month = 'September', NOT mf.month = 9
4. Use proper aggregation (SUM for totals)"""

        payload = {
            "model": "anthropic/claude-3-haiku",
            "messages": [{"role": "user", "content": context}],
            "temperature": 0.1,
            "max_tokens": 500
        }

        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "HTTP-Referer": "http://localhost:5001",
                "X-Title": "DP World Maritime",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )

        if resp.status_code == 200:
            sql = resp.json()["choices"][0]["message"]["content"].strip()
            if sql.startswith('```'):
                sql = sql.split('```')[1].replace('sql', '').strip()
            return sql
        return None
    except Exception as e:
        st.error(f"LLM Error: {e}")
        return None

def get_narrative(question, data):
    """Generate narrative analysis using LLM"""
    if not data or not API_KEY:
        return f"Query returned {len(data) if data else 0} results for: {question}"

    try:
        summary = json.dumps(data[:5], indent=2)  # Show first 5 results

        payload = {
            "model": "anthropic/claude-3-haiku",
            "messages": [{
                "role": "user",
                "content": f"""Analyze this DP World Maritime Financial data and provide a brief business summary (2-3 paragraphs):

Question: {question}
Data Sample: {summary}

Keep it concise and focused on business insights."""
            }],
            "temperature": 0.7,
            "max_tokens": 400
        }

        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "HTTP-Referer": "http://localhost:5001",
                "X-Title": "DP World Maritime",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )

        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        return f"Data retrieved: {len(data)} rows"
    except:
        return f"Data retrieved: {len(data)} rows"

def execute_query(question, unit='Africa'):
    """Execute query and return results"""
    msg = question.lower()
    sql = None

    # Detect units
    has_africa = 'africa' in msg
    has_mena = 'mena' in msg
    if has_africa and has_mena:
        unit = None
    elif has_africa:
        unit = 'Africa'
    elif has_mena:
        unit = 'MENA'

    # Pattern 1: Actual vs Budget
    if any(x in msg for x in ['actual', 'budget', 'variance']):
        words = msg.split()
        exclude_words = ['show', 'display', 'give', 'me', 'the', 'actual', 'vs', 'budget', 'variance', 'for', 'cost', 'in', 'a', 'and', 'fees', 'charges', 'expense', 'africa', 'mena']
        category = ' '.join([w for w in words if w not in exclude_words and len(w) > 2])
        if not category:
            category = 'revenue'
        category = get_category_mapping(category)
        unit_filter = f"u.unit_name = '{unit}'" if unit else "1=1"
        sql = f"""SELECT u.unit_name, pc.category_name,
       ROUND(SUM(mf.actual), 2) as actual,
       ROUND(SUM(mf.budget), 2) as budget,
       ROUND(SUM(mf.actual) - SUM(mf.budget), 2) as variance
FROM monthly_financials mf
JOIN pl_categories pc ON mf.category_id = pc.category_id
JOIN vessels v ON mf.vessel_id = v.vessel_id
JOIN units u ON v.unit_id = u.unit_id
WHERE {unit_filter} AND pc.category_name LIKE '%{category}%'
GROUP BY u.unit_name, pc.category_name"""

    # Pattern 2: By vessel
    elif 'by vessel' in msg or 'per vessel' in msg:
        unit_filter = f"u.unit_name = '{unit}'" if unit else "1=1"
        sql = f"""SELECT u.unit_name, v.vessel_name,
       ROUND(SUM(mf.actual), 2) as total
FROM monthly_financials mf
JOIN vessels v ON mf.vessel_id = v.vessel_id
JOIN units u ON v.unit_id = u.unit_id
WHERE {unit_filter}
GROUP BY u.unit_name, v.vessel_name
ORDER BY u.unit_name, total DESC"""

    # Pattern 3: Vessel + Date + Category
    elif ('topaz' in msg or 'ever' in msg or 'vessel' in msg) and ('september' in msg or 'january' in msg or 'february' in msg or '2024' in msg or '2023' in msg):
        vessel_match = re.search(r'(topaz \w+|ever \w+)', msg)
        vessel_name = vessel_match.group(0).title() if vessel_match else None

        months = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
        month = next((m for m in months if m in msg), None)

        year_match = re.search(r'20\d{2}', msg)
        year = year_match.group(0) if year_match else '2024'

        # Extract category
        words = msg.split()
        exclude = ['give', 'me', 'for', 'in', 'the', 'show', 'display', 'africa', 'mena', 'vessel', 'topaz', 'resolve', 'commander', 'ever', 'given', 'and', '&'] + months + [year]
        category_words = []
        for i, w in enumerate(words):
            if w not in exclude:
                if w == '-' and i > 0 and i < len(words) - 1:
                    category_words.append(w)
                elif w == '&':
                    category_words.append(w)
                elif len(w) > 2:
                    category_words.append(w)
        category = ' '.join(category_words) if category_words else None
        if category:
            category = get_category_mapping(category)

        if vessel_name and month and category:
            month_name = month.capitalize()
            sql = f"""SELECT u.unit_name, v.vessel_name, pc.category_name, mf.year, mf.month, mf.actual, mf.budget, mf.last_year
FROM monthly_financials mf
JOIN vessels v ON mf.vessel_id = v.vessel_id
JOIN units u ON v.unit_id = u.unit_id
JOIN pl_categories pc ON mf.category_id = pc.category_id
WHERE v.vessel_name LIKE '%{vessel_name.split()[-1]}%'
  AND mf.month = '{month_name}'
  AND mf.year = {year}
  AND pc.category_name = '{category}'"""

    # Pattern 4: Generic category
    elif any(x in msg for x in ['total', 'how much', 'cost', 'expense', 'ebitda', 'revenue', 'pat', 'ebit', 'margin', 'insurance', 'fuel', 'payroll', 'charter', 'port', 'fees']):
        words = msg.split()
        exclude = ['give', 'me', 'the', 'show', 'what', 'is', 'are', 'for', 'total', 'how', 'much', 'of', 'actual', 'vs', 'budget', 'in', 'a', 'and', 'display', 'africa', 'mena', 'can', 'you', 'get', 'please']
        category = ' '.join([w for w in words if w not in exclude and len(w) > 2])
        if not category or category == '':
            category = 'revenue'
        category = get_category_mapping(category)
        unit_filter = f"u.unit_name = '{unit}'" if unit else "1=1"
        sql = f"""SELECT u.unit_name, pc.category_name,
       ROUND(SUM(mf.actual), 2) as total
FROM monthly_financials mf
JOIN pl_categories pc ON mf.category_id = pc.category_id
JOIN vessels v ON mf.vessel_id = v.vessel_id
JOIN units u ON v.unit_id = u.unit_id
WHERE {unit_filter} AND pc.category_name LIKE '%{category}%'
GROUP BY u.unit_name, pc.category_name
ORDER BY u.unit_name, total DESC"""

    # Fallback to LLM
    if not sql:
        sql = get_llm_sql(question, unit)
        if not sql:
            return None, None, None

    # Fix month format
    sql = fix_month_in_sql(sql)

    # Execute
    result = query_db(sql)
    if not result['ok']:
        return None, None, None

    data = result['data']
    narrative = get_narrative(question, data)
    return data, narrative, sql

# Streamlit UI
st.title("Financial Intelligence Dashboard")
st.markdown("Analyze vessel operations, budgets, and financial performance with AI-powered insights")

# Sidebar with query categories
with st.sidebar:
    st.header("Maritime FP&A")
    st.markdown("Financial analysis for your fleet")
    st.markdown("---")

    unit = st.selectbox("Business Unit", ["Africa", "MENA"])

    st.markdown("---")
    st.subheader("BASIC - Simple Totals")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Total Revenue", use_container_width=True):
            st.session_state.query = "Total Revenue"
        if st.button("EBITDA", use_container_width=True):
            st.session_state.query = "EBITDA for Africa"
    with col2:
        if st.button("Operating Costs", use_container_width=True):
            st.session_state.query = "Total Operating Cost"
        if st.button("Overheads", use_container_width=True):
            st.session_state.query = "Total Overheads"

    st.markdown("---")
    st.subheader("BASIC - By Vessel")
    if st.button("Crew Costs by Vessel", use_container_width=True):
        st.session_state.query = "Crew cost by vessel"
    if st.button("Operating Costs by Vessel", use_container_width=True):
        st.session_state.query = "Operating costs by vessel"
    if st.button("Insurance by Vessel", use_container_width=True):
        st.session_state.query = "Insurance costs by vessel"
    if st.button("Charter Hire by Vessel", use_container_width=True):
        st.session_state.query = "Charter Hire by vessel"

    st.markdown("---")
    st.subheader("INTERMEDIATE - Variance")
    if st.button("Crew Payroll Variance", use_container_width=True):
        st.session_state.query = "Crew Payroll Cost actual vs budget"
    if st.button("Charter Hire Variance", use_container_width=True):
        st.session_state.query = "Charter Hire actual vs budget"
    if st.button("Port Charges Variance", use_container_width=True):
        st.session_state.query = "Port Handling Charges actual vs budget"
    if st.button("Insurance Variance", use_container_width=True):
        st.session_state.query = "Insurance actual vs budget"

    st.markdown("---")
    st.subheader("ADVANCED - Metrics")
    if st.button("Crew Payroll by Vessel", use_container_width=True):
        st.session_state.query = "Crew Payroll Cost by vessel"
    if st.button("Fuel Costs by Vessel", use_container_width=True):
        st.session_state.query = "Fuel and Water by vessel"
    if st.button("EBIT Analysis", use_container_width=True):
        st.session_state.query = "EBIT for Africa"
    if st.button("Profit After Tax", use_container_width=True):
        st.session_state.query = "PAT for Africa"

    st.markdown("---")
    st.info("Tip: You can also ask custom questions about your financial data. The AI will intelligently route your query.")

# Main content area
col1, col2 = st.columns([3, 1], gap="small")
with col1:
    st.markdown("### Your Question")
with col2:
    pass

# Input area
input_col, btn_col = st.columns([4, 1], gap="small")
with input_col:
    user_query = st.text_input(
        "Enter your question",
        value=st.session_state.get("query", ""),
        placeholder="Ask about costs, revenue, ratios, variance...",
        label_visibility="collapsed",
        key="user_input"
    )
with btn_col:
    send_btn = st.button("Send", use_container_width=True)

# Process query
if send_btn or (st.session_state.get("query") and user_query):
    query_to_run = user_query if user_query else st.session_state.get("query", "")

    if query_to_run:
        st.session_state.query = ""  # Clear for next use

        st.markdown("---")
        st.markdown(f"**Query:** {query_to_run}")

        with st.spinner("Processing your query..."):
            data, narrative, sql = execute_query(query_to_run, unit)

        if data:
            st.success(f"Found {len(data)} result(s)")

            # Summary section with narrative
            st.markdown("### Summary")
            st.markdown(narrative if narrative else "Query executed successfully.")

            # Data section
            st.markdown("### Data")
            st.dataframe(data, use_container_width=True, hide_index=True)

            # Show SQL query in expander
            if sql:
                with st.expander("View SQL Query"):
                    st.code(sql, language="sql")

            # Show metadata
            with st.expander("Metadata"):
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Records", len(data))
                with col2:
                    st.metric("Unit", unit)
        else:
            st.error("No results found. Try rephrasing your question or select a different query from the sidebar.")
