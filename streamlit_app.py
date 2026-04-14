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

PATTERN 4 - Vessel breakdown (aggregate) - FOR "by vessel" QUERIES:
SELECT v.vessel_name, pc.category_name, SUM(mf.actual) as total
FROM monthly_financials mf
JOIN vessels v ON mf.vessel_id = v.vessel_id
JOIN units u ON v.unit_id = u.unit_id
JOIN pl_categories pc ON mf.category_id = pc.category_id
WHERE pc.category_name = 'Crew Salaries'
GROUP BY v.vessel_name, pc.category_name
ORDER BY total DESC

PATTERN 4B - BY VESSEL WITH UNIT:
SELECT u.unit_name, v.vessel_name, SUM(mf.actual) as total
FROM monthly_financials mf
JOIN vessels v ON mf.vessel_id = v.vessel_id
JOIN units u ON v.unit_id = u.unit_id
JOIN pl_categories pc ON mf.category_id = pc.category_id
WHERE pc.category_name = 'Operating Costs'
GROUP BY u.unit_name, v.vessel_name
ORDER BY total DESC

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

MARGIN HANDLING (IMPORTANT):
- Margin categories: EBITDA Margin, EBIT Margin, PAT Margin
- These are decimal ratios (e.g., 0.15 means 15%)
- In queries, multiply margins by 100 for display: ROUND(mf.actual * 100, 2) as margin_pct
- NEVER aggregate margins with RC/currency line items (don't SUM them together)
- ALWAYS exclude rows where ABS(margin) > 10 (these are data anomalies)
- When querying margins, use: WHERE ABS(mf.actual) <= 10 AND pc.category_name IN ('EBITDA Margin', 'EBIT Margin', 'PAT Margin')

FILTER & QUERY TYPE INSTRUCTIONS:
- "by vessel", "vessel breakdown", "each vessel" = use PATTERN 4 or 4B (group by v.vessel_name, ORDER BY DESC)
- "by unit", "Africa", "MENA" = use PATTERN 1 (group by u.unit_name)
- "compare", "vs", "comparison" = MUST include both units (WHERE ... IN ('Africa', 'MENA')) or both actual+budget
- "actual vs budget", "variance", "over/under" = use PATTERN 3 (select actual, budget, variance columns)
- "by month", "monthly", "trend", "this year" = use PATTERN 6 (monthly breakdown with year filter)
- "non-zero" or "non-negative" = WHERE mf.actual != 0 or WHERE mf.actual > 0
- "details", "breakdown", "show all", "list" = use PATTERN 5 (detail rows, no GROUP BY)
- "total", "sum", "how much" = use aggregate pattern with SUM() and GROUP BY
- "highest", "lowest", "top", "rank" = use PATTERN 4 with ORDER BY DESC/ASC
- "tell me about" = provide monthly breakdown + totals to show trends and context
- Database contains only 2024 data. Always use WHERE year = 2024
- If user asks about current year (2026) or future years, note that only 2024 data is available
- CRITICAL: When user asks to "compare", ensure the WHERE clause includes BOTH conditions (don't filter to just one unit)

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
                "content": f"""You are a maritime finance business analyst. Analyze this data and provide KEY INSIGHTS (2-3 paragraphs).

FOCUS ON INSIGHTS, NOT JUST DATA:
- What does this data reveal about business performance?
- Highlight significant trends, anomalies, or noteworthy patterns
- Compare values meaningfully (e.g., "twice as high", "significantly exceeded")
- Explain business implications
- Identify opportunities or concerns

CRITICAL FORMATTING RULES - YOU MUST FOLLOW EXACTLY:
- Put space after EVERY comma: "1,000, the result" NOT "1,000,the"
- Put space after EVERY period: "result. The next" NOT "result.The"
- Put space BETWEEN all words: "while the" NOT "whilethe"
- Use RC currency: "RC 5,234" or "$5,234"
- NEVER concatenate words together
- Write numbers clearly: "5,234" with comma separator
- Always: "and the company" NOT "andthecompany"
- Always: "from month to month" NOT "frommonthtomonth"

Data Summary: {summary}
Question Asked: {question}

Write 2-3 paragraphs with PROPER SPACING and RC currency.
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
    """Generate chart with clear logic"""
    if not data or len(data) < 1:
        return None

    try:
        df = pd.DataFrame(data)
        cols = list(df.columns)
        question_lower = question.lower()

        if len(df) < 2:
            return None

        # Detect column types
        numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
        text_cols = [c for c in cols if pd.api.types.is_object_dtype(df[c])]

        if not numeric_cols:
            return None

        # Detect special columns
        has_month = any('month' in c.lower() for c in cols)
        has_vessel = any('vessel' in c.lower() for c in cols)
        has_actual = any('actual' in c.lower() for c in numeric_cols)
        has_budget = any('budget' in c.lower() for c in numeric_cols)
        has_multiple_numeric = len(numeric_cols) > 1

        # Logic 1: If asking for comparison or vs → BAR CHART (grouped bars)
        if any(word in question_lower for word in ['compare', ' vs ', 'vs ', ' vs', 'comparison']):
            return _create_bar_chart(df, text_cols, numeric_cols, question)

        # Logic 2: If asking for actual vs budget → BAR CHART (grouped)
        if has_actual and has_budget:
            return _create_bar_chart(df, text_cols, numeric_cols, question)

        # Logic 3: If asking for ranking/highest/lowest → HORIZONTAL BAR
        if any(word in question_lower for word in ['highest', 'lowest', 'top', 'rank']):
            return _create_horizontal_bar_chart(df, text_cols, numeric_cols[0], question)

        # Logic 4: If asking for by vessel → HORIZONTAL BAR (sorted)
        if 'by vessel' in question_lower or 'each vessel' in question_lower:
            return _create_horizontal_bar_chart(df, text_cols, numeric_cols[0], question)

        # Logic 5: If has months → LINE CHART (PRIORITY)
        if has_month:
            month_col = [c for c in cols if 'month' in c.lower()][0]
            return _create_line_chart(df, month_col, numeric_cols)

        # Logic 6: Default for multiple numeric columns → BAR CHART
        if has_multiple_numeric and text_cols:
            return _create_bar_chart(df, text_cols, numeric_cols, question)

        # Logic 7: Default for single numeric + text → HORIZONTAL BAR
        if text_cols and len(numeric_cols) == 1:
            return _create_horizontal_bar_chart(df, text_cols, numeric_cols[0], question)

        return None

    except Exception as e:
        return None


def _create_bar_chart(df, text_cols, numeric_cols, question=""):
    """Create grouped bar chart for comparisons"""
    import plotly.graph_objects as go

    if not text_cols or not numeric_cols:
        return None

    x_col = text_cols[0]
    fig = go.Figure()

    colors = ['#0078D4', '#A8A8A8', '#107C10', '#FFB900', '#E74C3C']

    # Add bars for each numeric column
    for i, col in enumerate(numeric_cols):
        fig.add_trace(go.Bar(
            x=df[x_col],
            y=df[col],
            name=col,
            marker_color=colors[i % len(colors)]
        ))

    title = question[:60] + "..." if len(question) > 60 else question

    fig.update_layout(
        title=title,
        xaxis_title=x_col,
        yaxis_title="Amount (RC)",
        barmode='group',
        template='plotly_white',
        height=450,
        font=dict(size=11),
        hovermode='x unified'
    )
    return fig


def _create_line_chart(df, month_col, numeric_cols):
    """RULE 1: Line chart for trends over time"""
    import plotly.graph_objects as go
    month_order = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']

    df_sorted = df.copy()
    df_sorted['_month_sort'] = df_sorted[month_col].apply(
        lambda x: month_order.index(str(x)) if str(x) in month_order else 0
    )
    df_sorted = df_sorted.sort_values('_month_sort')

    fig = go.Figure()
    colors = ['#0078D4', '#107C10', '#E74C3C', '#FFB900', '#7B68EE']

    for i, col in enumerate(numeric_cols):
        fig.add_trace(go.Scatter(
            x=df_sorted[month_col],
            y=df_sorted[col],
            mode='lines+markers',
            name=col,
            line=dict(color=colors[i % len(colors)], width=2),
            marker=dict(size=6)
        ))

    fig.update_layout(
        title=f"Trend Analysis - {', '.join(numeric_cols)}",
        xaxis_title="Month",
        yaxis_title="Value (RC)",
        template='plotly_white',
        height=450,
        hovermode='x unified',
        font=dict(size=11)
    )
    return fig


def _create_grouped_bar_chart(df, month_col, actual_col, budget_col, ly_col):
    """RULE 2: Grouped bar chart for Actual vs Budget vs LY"""
    import plotly.graph_objects as go

    fig = go.Figure()

    if month_col:
        month_order = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December']
        df_sorted = df.copy()
        df_sorted['_month_sort'] = df_sorted[month_col].apply(
            lambda x: month_order.index(str(x)) if str(x) in month_order else 0
        )
        df_sorted = df_sorted.sort_values('_month_sort')
        x_vals = df_sorted[month_col]
    else:
        df_sorted = df
        x_vals = range(len(df))

    fig.add_trace(go.Bar(x=x_vals, y=df_sorted[actual_col], name='Actual', marker_color='#0078D4'))
    if budget_col:
        fig.add_trace(go.Bar(x=x_vals, y=df_sorted[budget_col], name='Budget', marker_color='#A8A8A8'))
    if ly_col:
        fig.add_trace(go.Bar(x=x_vals, y=df_sorted[ly_col], name='Last Year', marker_color='#107C10'))

    fig.update_layout(
        title="Actual vs Budget Analysis",
        xaxis_title="Period",
        yaxis_title="Amount (RC)",
        barmode='group',
        template='plotly_white',
        height=450,
        font=dict(size=11)
    )
    return fig


def _create_horizontal_bar_chart(df, text_cols, value_col, question=""):
    """RULE 3: Horizontal bar chart for ranking"""
    import plotly.graph_objects as go

    df_sorted = df.sort_values(value_col, ascending=True)
    x_col = text_cols[0]

    # Format values with RC currency
    formatted_values = [f"RC {v:,.0f}" if pd.notna(v) else "" for v in df_sorted[value_col]]

    fig = go.Figure(data=[
        go.Bar(
            y=df_sorted[x_col],
            x=df_sorted[value_col],
            orientation='h',
            marker_color=['#0078D4' if v >= 0 else '#E74C3C' for v in df_sorted[value_col]],
            text=formatted_values,
            textposition='auto'
        )
    ])

    # Generate title from question if available
    if question:
        title = question[:50] + "..." if len(question) > 50 else question
    else:
        title = f"{value_col} by {x_col}"

    fig.update_layout(
        title=title,
        xaxis_title=f"{value_col} (RC)",
        yaxis_title=x_col,
        template='plotly_white',
        height=max(300, len(df) * 35),
        font=dict(size=11),
        showlegend=False
    )
    return fig


def _create_diverging_bar_chart(df, actual_col, budget_col, month_col):
    """RULE 4: Diverging bar chart for variance"""
    import plotly.graph_objects as go

    df['variance'] = df[actual_col] - df[budget_col]
    df_sorted = df.sort_values('variance')

    x_label = df_sorted[month_col] if month_col else df_sorted.index

    fig = go.Figure(data=[
        go.Bar(
            x=df_sorted['variance'],
            y=x_label,
            orientation='h',
            marker_color=['#107C10' if v >= 0 else '#E74C3C' for v in df_sorted['variance']],
            text=[f"RC {v:,.0f}" for v in df_sorted['variance']],
            textposition='auto'
        )
    ])

    fig.add_vline(x=0, line_dash="dash", line_color="black")

    fig.update_layout(
        title="Variance Analysis (Actual vs Budget)",
        xaxis_title="Variance (RC)",
        template='plotly_white',
        height=450,
        font=dict(size=11)
    )
    return fig


def _create_margin_trend_chart(df, month_col, numeric_cols):
    """RULE 5: Dual-axis chart with margin % and underlying USD"""
    import plotly.graph_objects as go

    margin_cols = [c for c in numeric_cols if 'margin' in c.lower()]
    usd_cols = [c for c in numeric_cols if 'margin' not in c.lower()]

    if not margin_cols:
        return _create_line_chart(df, month_col, numeric_cols)

    month_order = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']
    df_sorted = df.copy()
    df_sorted['_month_sort'] = df_sorted[month_col].apply(
        lambda x: month_order.index(str(x)) if str(x) in month_order else 0
    )
    df_sorted = df_sorted.sort_values('_month_sort')

    fig = go.Figure()

    # Add USD bars on left axis
    if usd_cols:
        for col in usd_cols:
            fig.add_trace(go.Bar(x=df_sorted[month_col], y=df_sorted[col], name=col, yaxis='y1'))

    # Add margin lines on right axis
    for col in margin_cols:
        fig.add_trace(go.Scatter(
            x=df_sorted[month_col],
            y=df_sorted[col] * 100,
            mode='lines+markers',
            name=f"{col} %",
            yaxis='y2',
            line=dict(width=2)
        ))

    fig.update_layout(
        title="Margin Analysis",
        xaxis_title="Month",
        yaxis=dict(title="Amount (RC)", side='left'),
        yaxis2=dict(title="Margin (%)", overlaying='y', side='right'),
        template='plotly_white',
        height=450,
        hovermode='x unified',
        font=dict(size=11)
    )
    return fig


def _create_heatmap_table(df, vessel_col, numeric_cols):
    """RULE 6: Heatmap for multi-vessel summary"""
    import plotly.graph_objects as go

    fig = go.Figure(data=go.Heatmap(
        z=[df[col].values for col in numeric_cols],
        x=df[vessel_col].values,
        y=numeric_cols,
        colorscale='RdYlGn'
    ))

    fig.update_layout(
        title="Multi-Vessel Summary",
        xaxis_title="Vessel",
        yaxis_title="Metric",
        template='plotly_white',
        height=400,
        font=dict(size=11)
    )
    return fig

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
with st.form("query_form", clear_on_submit=False):
    user_query = st.text_input(
        "Enter your question",
        value=st.session_state.get("query", ""),
        placeholder="Ask about costs, revenue, ratios, variance... (Press Enter or click Send)",
        label_visibility="collapsed",
        key="user_input"
    )
    col1, col2 = st.columns([4, 1])
    with col1:
        st.empty()
    with col2:
        send_btn = st.form_submit_button("Send", use_container_width=True)

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
                clean_narrative = narrative

                # Fix common spacing issues after punctuation
                clean_narrative = re.sub(r'\.([A-Z])', r'. \1', clean_narrative)  # .The -> . The
                clean_narrative = re.sub(r',([A-Za-z])', r', \1', clean_narrative)  # ,the -> , the

                # Fix concatenated lowercase words (e.g., "frommonth" -> "from month")
                clean_narrative = re.sub(r'([a-z])([a-z]{3,}(?:from|to|and|the|is|was|has|while|which|during|month|year|between))',
                                        lambda m: f"{m.group(1)} {m.group(2)}" if m.group(2).lower() in ['from', 'to', 'and', 'the', 'is', 'was', 'has', 'while', 'which', 'during', 'month', 'year', 'between'] else m.group(0),
                                        clean_narrative, flags=re.IGNORECASE)

                # Fix lowercase to uppercase transitions (e.g., "whileThe" -> "while The")
                clean_narrative = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean_narrative)

                # Fix numbers concatenated with words
                clean_narrative = re.sub(r'(\d)([a-z])', r'\1 \2', clean_narrative)  # 5the -> 5 the
                clean_narrative = re.sub(r'([a-z])(\d)', r'\1 \2', clean_narrative)  # the5 -> the 5

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
            # Format margin columns as percentages
            display_data = pd.DataFrame(data)
            for col in display_data.columns:
                if 'margin' in col.lower() and col not in ['unit_name', 'vessel_name', 'category_name', 'month', 'year']:
                    # Check if values are already percentages (if max > 100, assume already multiplied)
                    if display_data[col].max() < 100 and display_data[col].min() > -100:
                        # Format as percentage
                        display_data[col] = display_data[col].apply(lambda x: f"{x*100:.2f}%" if pd.notna(x) else x)
            st.dataframe(display_data, use_container_width=True, hide_index=True)

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