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
import time
import plotly.graph_objects as go
import pandas as pd

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

def validate_sql(sql):
    """Validate and attempt to execute SQL to catch errors early"""
    sql_upper = sql.upper()

    # Check for common issues:
    # 1. Using pc.* without JOIN to pl_categories
    if 'pc.' in sql and 'JOIN pl_categories pc' not in sql_upper:
        return False, "Missing JOIN pl_categories"

    # 2. Using u.* without proper unit join chain
    if 'u.unit_name' in sql and 'JOIN units u' not in sql_upper:
        return False, "Missing JOIN units"

    # 3. Check for ambiguous column references or missing JOINs
    if sql_upper.count('JOIN pl_categories pc') > 1:
        return False, "Duplicate pl_categories JOIN"

    return True, "OK"

def fix_sql_joins(sql, question):
    """Fix common SQL generation errors"""
    sql_upper = sql.upper()

    # ONLY add JOIN if truly missing
    if 'pc.' in sql and 'JOIN pl_categories pc' not in sql_upper:
        # Find the position to insert the JOIN
        where_pos = sql_upper.find('WHERE')
        if where_pos < 0:
            where_pos = sql_upper.find('GROUP')
        if where_pos < 0:
            where_pos = len(sql)

        # Insert the JOIN before WHERE/GROUP
        join_clause = '\nJOIN pl_categories pc ON mf.category_id = pc.category_id'
        sql = sql[:where_pos].rstrip() + join_clause + '\n' + sql[where_pos:]

    return sql

def get_llm_sql(question, unit):
    """Ask LLM to generate SQL"""
    if not API_KEY:
        return None

    try:
        # Include ALL categories so LLM knows what's available
        all_categories_str = ', '.join(ALL_CATEGORIES)

        context = f"""You are generating SQL for DP World Maritime Financial Analysis.

DATABASE STRUCTURE:
- units (u): unit_id, unit_name ('Africa' or 'MENA')
- vessels (v): vessel_id, vessel_name, unit_id
- pl_categories (pc): category_id, category_name
- monthly_financials (mf): vessel_id, category_id, year, month (TEXT), actual, budget, last_year, risk_factor_10

FOREIGN KEYS:
  mf.vessel_id → v.vessel_id
  mf.category_id → pc.category_id
  v.unit_id → u.unit_id

IMPORTANT COLUMN NOTES:
- month is TEXT: 'January', 'February', ... 'December' (NEVER use numbers 1, 2, 3)
- actual and budget are COLUMNS for variance analysis (not categories)
- year is INTEGER - IMPORTANT: Database only contains 2024 data
- When user asks for "this year" or current year data, use 2024 (that's all we have)
- If user asks about 2026 or current year, explain we only have 2024 financial data available

AVAILABLE CATEGORIES (ALL {len(ALL_CATEGORIES)} of them):
{all_categories_str}

QUERY PATTERNS - Copy the Join structure exactly:

PATTERN 1 - Aggregated by unit (totals):
SELECT u.unit_name, SUM(mf.actual) as total
FROM monthly_financials mf
JOIN vessels v ON mf.vessel_id = v.vessel_id
JOIN units u ON v.unit_id = u.unit_id
JOIN pl_categories pc ON mf.category_id = pc.category_id
WHERE u.unit_name IN ('Africa', 'MENA')
GROUP BY u.unit_name

PATTERN 2 - Category total (aggregate):
SELECT pc.category_name, SUM(mf.actual) as total
FROM monthly_financials mf
JOIN pl_categories pc ON mf.category_id = pc.category_id
WHERE pc.category_name = 'Crew Salaries'
GROUP BY pc.category_name

PATTERN 3 - Variance analysis (aggregate):
SELECT u.unit_name, pc.category_name, SUM(mf.actual) as actual, SUM(mf.budget) as budget, SUM(mf.actual - mf.budget) as variance
FROM monthly_financials mf
JOIN vessels v ON mf.vessel_id = v.vessel_id
JOIN units u ON v.unit_id = u.unit_id
JOIN pl_categories pc ON mf.category_id = pc.category_id
WHERE pc.category_name = 'Crew Salaries'
GROUP BY u.unit_name, pc.category_name

PATTERN 4 - Vessel breakdown (aggregate):
SELECT u.unit_name, v.vessel_name, pc.category_name, SUM(mf.actual) as total
FROM monthly_financials mf
JOIN vessels v ON mf.vessel_id = v.vessel_id
JOIN units u ON v.unit_id = u.unit_id
JOIN pl_categories pc ON mf.category_id = pc.category_id
WHERE pc.category_name = 'Crew Salaries'
GROUP BY u.unit_name, v.vessel_name, pc.category_name

PATTERN 5 - DETAIL ROWS (when user asks for "details", "breakdown", "all values", "non-zero", etc - NO GROUP BY):
SELECT u.unit_name, v.vessel_name, mf.year, mf.month, pc.category_name, mf.actual, mf.budget
FROM monthly_financials mf
JOIN vessels v ON mf.vessel_id = v.vessel_id
JOIN units u ON v.unit_id = u.unit_id
JOIN pl_categories pc ON mf.category_id = pc.category_id
WHERE pc.category_name = 'Crew Salaries' AND mf.actual != 0
ORDER BY u.unit_name, v.vessel_name, mf.year, mf.month

PATTERN 6 - MONTHLY BREAKDOWN (when user asks for "by month", "monthly", "trend", "this year", "breakdown by month"):
SELECT mf.month, pc.category_name, SUM(mf.actual) as actual, SUM(mf.budget) as budget
FROM monthly_financials mf
JOIN pl_categories pc ON mf.category_id = pc.category_id
WHERE pc.category_name = 'EBITDA' AND mf.year = 2024
GROUP BY mf.month, pc.category_name
ORDER BY CASE WHEN mf.month='January' THEN 1 WHEN mf.month='February' THEN 2 WHEN mf.month='March' THEN 3 WHEN mf.month='April' THEN 4 WHEN mf.month='May' THEN 5 WHEN mf.month='June' THEN 6 WHEN mf.month='July' THEN 7 WHEN mf.month='August' THEN 8 WHEN mf.month='September' THEN 9 WHEN mf.month='October' THEN 10 WHEN mf.month='November' THEN 11 ELSE 12 END

FILTER & QUERY TYPE INSTRUCTIONS:
- "non-zero" or "non-negative" = WHERE mf.actual != 0 or WHERE mf.actual > 0
- "details", "breakdown", "show all", "list" = use PATTERN 5 (detail rows, no GROUP BY)
- "by month", "monthly", "trend", "this year" = use PATTERN 6 (monthly breakdown with year filter)
- "compare", "vs", "variance" = use variance pattern with GROUP BY
- "total", "sum", "how much" = use aggregate pattern with SUM() and GROUP BY
- "tell me about" = provide monthly breakdown + totals to show trends and context
- Database contains only 2024 data. Always use WHERE year = 2024
- If user asks about current year (2026) or future years, note that only 2024 data is available

CRITICAL - Answer with ONLY SQL, nothing else. No explanation, no code blocks, no markdown.
Task: "{question}"
SQL:"""

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
            response = resp.json()["choices"][0]["message"]["content"].strip()
            sql = response

            # Extract SQL from code block if present
            if '```sql' in sql or '```' in sql:
                parts = sql.split('```')
                for part in parts:
                    if 'SELECT' in part.upper():
                        sql = part.replace('sql', '').strip()
                        break

            # Find SELECT statement
            if 'SELECT' not in sql.upper():
                return None

            select_pos = sql.upper().find('SELECT')
            sql = sql[select_pos:].strip()

            # Simple cleanup: if there's a semicolon, take up to and including it
            if ';' in sql:
                sql = sql[:sql.find(';') + 1]
            else:
                sql = sql + ';'

            if not ('FROM' in sql.upper()):
                return None

            return sql
        return None
    except Exception as e:
        st.error(f"LLM Error: {e}")
        return None

def get_narrative(question, data):
    """Generate narrative analysis using LLM with rate limiting"""
    if not data:
        return None

    if not API_KEY:
        return None

    try:
        # Rate limiting - wait between LLM calls to avoid hitting rate limits
        if "last_llm_call" not in st.session_state:
            st.session_state.last_llm_call = 0

        current_time = time.time()
        time_since_last = current_time - st.session_state.last_llm_call
        if time_since_last < 3:  # 3 second cooldown between requests
            st.session_state.message = f"Rate limiting: waiting {3 - int(time_since_last)} seconds..."
            time.sleep(3 - time_since_last)
        st.session_state.last_llm_call = time.time()

        summary = json.dumps(data[:5], indent=2)  # Show first 5 results

        payload = {
            "model": "anthropic/claude-3-haiku",
            "messages": [{
                "role": "user",
                "content": f"""You are a financial analyst. Analyze this data and write a brief summary (2-3 paragraphs).

CRITICAL FORMATTING RULES - MUST FOLLOW:
- ALWAYS put a space after commas and periods
- ALWAYS put spaces between words
- NEVER concatenate words together
- Write numbers as: "45,973 million" (with comma and space)
- NEVER write "million," without space after it
- Example WRONG: "whilethebudgetwas0"
- Example RIGHT: "while the budget was 0"

Data Summary: {summary}
Question Asked: {question}

Write 2-3 paragraphs. Remember: ALWAYS use proper spacing between words and after punctuation.
Note: We only have financial data for 2024. No other years are available."""
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
            result = resp.json()
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"].strip()
        elif resp.status_code == 429:
            st.warning("Rate limit reached. Please wait a moment before trying again.")
            return None
        else:
            st.warning(f"LLM API error: {resp.status_code}")
        return None
    except Exception as e:
        st.warning(f"Could not generate narrative: {str(e)}")
        return None

def generate_chart(question, data):
    """Generate chart using LLM suggestion"""
    if not data or len(data) < 2 or not API_KEY:
        return None

    try:
        df = pd.DataFrame(data)

        # Get column info
        cols = list(df.columns)
        numeric_cols = [c for c in cols if df[c].dtype in ['int64', 'float64', 'float32']]
        text_cols = [c for c in cols if df[c].dtype == 'object']

        if not numeric_cols:
            return None

        # Ask LLM what chart type would be best
        prompt = f"""Based on this question and data structure, what type of chart?

Question: {question}
Columns: {cols}
Has month column: {'month' in ' '.join(cols).lower()}

Answer with ONLY one word: 'line' OR 'bar' OR 'scatter'"""

        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "HTTP-Referer": "http://localhost:5001",
                "X-Title": "DP World Maritime",
                "Content-Type": "application/json"
            },
            json={
                "model": "anthropic/claude-3-haiku",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 10
            },
            timeout=30
        )

        if resp.status_code != 200:
            return None

        chart_type = resp.json()["choices"][0]["message"]["content"].strip().lower()

        # Create the chart based on LLM suggestion
        fig = go.Figure()
        x_col = text_cols[0] if text_cols else cols[0]
        y_col = numeric_cols[0]

        if 'line' in chart_type or 'month' in ' '.join(cols).lower():
            # Line chart for trends
            if 'month' in ' '.join(cols).lower():
                month_col = [c for c in cols if 'month' in c.lower()][0]
                month_order = ['January', 'February', 'March', 'April', 'May', 'June',
                              'July', 'August', 'September', 'October', 'November', 'December']
                df['_sort'] = df[month_col].apply(lambda x: month_order.index(str(x)) if str(x) in month_order else 0)
                df = df.sort_values('_sort')
                x_col = month_col

            fig.add_trace(go.Scatter(
                x=df[x_col],
                y=df[y_col],
                mode='lines+markers',
                line=dict(color='#00d084', width=3),
                marker=dict(size=8)
            ))
            title = 'Trend'
        else:
            # Bar chart for comparisons
            fig.add_trace(go.Bar(
                x=df[x_col],
                y=df[y_col],
                marker=dict(color='#00d084')
            ))
            title = 'Comparison'

        fig.update_layout(
            title=title,
            xaxis_title=str(x_col),
            yaxis_title=str(y_col),
            template='plotly_light',
            height=400
        )
        return fig

    except Exception as e:
        return None

def execute_query(question, unit='Africa'):
    """Execute query and return results - LLM analyzes and routes"""
    msg = question.lower()

    # Detect units from query
    has_africa = 'africa' in msg
    has_mena = 'mena' in msg
    if has_africa and has_mena:
        unit = None
    elif has_africa:
        unit = 'Africa'
    elif has_mena:
        unit = 'MENA'

    # LLM is the primary intelligence - analyze and generate SQL
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

# OLD PATTERN MATCHING CODE (kept for reference but not used)
def OLD_execute_query_patterns(question, unit='Africa'):
    """OLD VERSION - kept for reference only"""
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

# Streamlit UI - DP World Maritime FP&A Chatbot
# Display logo at top center
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("dp-world-vector-logo-2021-1.png", use_container_width=True)

st.markdown("<div style='border-bottom: 3px solid #00d084; margin: 10px 0;'></div>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888; font-size: 13px; padding-left: 160px;'>Maritime Financial Intelligence</p>", unsafe_allow_html=True)

st.title("Financial Intelligence Dashboard")
st.markdown("Analyze vessel operations, budgets, and financial performance with AI-powered insights")

# Sidebar with query categories
with st.sidebar:
    st.header("Maritime FP&A")
    st.markdown("Financial analysis for your fleet")
    st.markdown("---")

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
            data, narrative, sql = execute_query(query_to_run, None)

        if data:
            st.success(f"Found {len(data)} result(s)")

            # Summary section with narrative
            st.markdown("### Summary")
            if narrative:
                # Clean up narrative text - fix spacing issues
                clean_narrative = narrative.replace("million,", "million, ").replace("million.", "million. ")
                # Fix concatenated words like "whilethebudget" -> "while the budget"
                clean_narrative = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean_narrative)
                st.markdown(clean_narrative)
            else:
                st.markdown("Query executed successfully.")

            # Chart section - LLM generates chart code
            chart = generate_chart(query_to_run, data)
            if chart:
                st.markdown("### Visualization")
                st.plotly_chart(chart, use_container_width=True)

            # Data section
            st.markdown("### Data")
            st.dataframe(data, use_container_width=True, hide_index=True)

            # Show SQL query in expander
            if sql:
                with st.expander("View SQL Query"):
                    st.code(sql, language="sql")

            # Show metadata
            with st.expander("Metadata"):
                st.metric("Records", len(data))
        else:
            st.error("No results found. Try rephrasing your question or select a different query from the sidebar.")

# Add DP World logo at bottom right
st.markdown("---")
col1, col2 = st.columns([3, 1])
with col2:
    st.image("dp-world-vector-logo-2021-1.png", width=200)