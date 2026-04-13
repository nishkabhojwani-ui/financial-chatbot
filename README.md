# DP World Financial Chatbot - Requirements

## Project Overview

Build a professional financial analytics chatbot for DP World to analyze 123,399 financial records spanning 12 months of 2024 operational data across 4 global business units.

**Audience:** Executive presentation to DP World stakeholders  
**Data:** 12MB SQLite database with financial metrics (actual, budget, last_year, risk-adjusted)  
**Primary Use:** Financial analysis, reporting, variance analysis, trend comparison

---

## Functional Requirements

### 1. Chat Interface
- **Pure conversation-based UI** - User talks to the chatbot, gets responses
- **No prominent selection menus** at top - selections should be subtle or hidden
- **Message flow** - User message (right, blue) → Analysis results (left, white)
- **Professional styling** - Clean, minimal, suitable for executive presentation

### 2. Query Execution
- **6 Standard Query Types:**
  1. Revenue Analysis - By unit, vessel, category
  2. Operating Costs - By category, unit
  3. Budget Variance - Actual vs Budget
  4. Unit Performance - Revenue comparison
  5. Year-over-Year - Current vs Prior year
  6. Risk Assessment - Risk-adjusted forecasts

- **3 Complexity Levels** (Simple → Medium → Complex):
  - **Simple:** Aggregated summaries, single dimension breakdowns
  - **Medium:** Multi-dimensional analysis, additional details
  - **Complex:** Full detail rows, all metrics, advanced calculations

### 3. Results Display
- **Inline in chat** - Results appear as part of conversation flow
- **Generated SQL visible** - Show the query that ran
- **Key metrics** - Top 4 numeric values displayed as cards
- **Charts** - Bar charts, pie charts for distribution
- **Data table** - Full results in scrollable table
- **Export options** - CSV and Excel download buttons

### 4. User Interactions
- **Type questions** - Free-text queries about financial data
- **Click suggested queries** - Pre-built query cards for quick analysis
- **Select complexity** - Choose data depth (Simple/Medium/Complex)
- **Download results** - Export to CSV or Excel

---

## Non-Functional Requirements

### Performance
- Query execution < 2 seconds
- UI responsive and smooth
- Handle 100+ concurrent users (if web-deployed)

### Design
- **DP World branding** - Use company colors and logo from dpworld.com
- **Professional appearance** - Suitable for C-level executives
- **Responsive** - Works on desktop (primary), tablet (optional)
- **Accessibility** - Clear text, good contrast, readable fonts

### Reliability
- Graceful error handling for failed queries
- API credit monitoring and fallback messaging
- Database connection validation

### Security
- Do NOT expose database connection strings in UI
- Validate all user inputs
- Sanitize SQL generation if using LLM
- No sensitive data in logs or error messages

---

## Technology Stack

### Backend
- **Database:** SQLite3 (financial_data.db)
- **API:** OpenRouter (GPT-4 for SQL generation) OR pure Python calculation
- **Language:** Python 3.8+
- **Framework:** Streamlit (fastest path) OR Flask/FastAPI

### Frontend
- **Framework:** Streamlit (built-in) OR React/Vue.js
- **Charts:** Plotly.js for interactive visualizations
- **Export:** Python libraries (pandas, openpyxl)

### Data Processing
- **Pandas:** Data manipulation, calculations
- **SQLite3:** Database queries

---

## Feature Requirements

### Core Features
- [x] Chat interface with message history
- [x] 6 standard financial query templates
- [x] 3 complexity levels per query
- [x] SQL query display
- [x] Key metrics cards (sum, count, etc.)
- [x] Chart visualizations (bar, pie)
- [x] Data table display
- [x] CSV export
- [x] Excel export

### Nice-to-Have
- [ ] PDF export with charts
- [ ] Custom date range filtering
- [ ] Saved favorites/bookmarks
- [ ] Query history
- [ ] Comparison between periods
- [ ] Trend analysis visualization
- [ ] Mobile responsive design

### Out of Scope (for now)
- Real AI chatbot with free-form questions
- Predictive analytics
- Multi-user collaboration
- Real-time data streaming
- Mobile app native version

---

## Data Quality Notes

- **Complete:** All 12 months represented, all 4 units included
- **Consistent:** Proper column names, normalized data types
- **Valid:** ~99% completeness, minor gaps acceptable
- **Duplicates:** Removed during preprocessing

---

## Success Criteria

1. **Functional:** All 6 queries work at all 3 complexity levels
2. **Visual:** Looks professional, suitable for DP World presentation
3. **Fast:** Results load in < 2 seconds
4. **Reliable:** Handles errors gracefully, no crashes
5. **Useful:** Executives can understand and export insights
6. **Branded:** DP World colors and logo integrated

---

## Getting Started

### Prerequisites
- Python 3.8+
- Streamlit OR Flask/FastAPI
- pandas, plotly, openpyxl
- SQLite3 (built-in)
- OpenRouter API key (optional, if using LLM)

### Project Structure
```
Financial_chatbot_dp_world/
├── financial_data.db        # SQLite database (123,399 records)
├── SCHEMA.md                # Database schema documentation
├── README.md                # This file
├── requirements.txt         # Python dependencies
├── app.py                   # Main application (to be created)
├── .env                     # API keys and config
└── /src                     # Source code (if using non-Streamlit)
```

### Installation
1. Create Python virtual environment
2. Install dependencies: `pip install -r requirements.txt`
3. Configure .env with OpenRouter API key (if needed)
4. Run: `streamlit run app.py` (or `python app.py` if Flask)

### Testing
- Verify database connection
- Test all 6 queries at each complexity level
- Check export functionality
- Validate styling and responsiveness

---

## Next Steps

1. **Design:** Create UI/UX mockups or wireframes
2. **Choose Stack:** Streamlit (fastest) or custom web framework
3. **Build Core:** Implement chat interface and query execution
4. **Add Features:** Charts, export, error handling
5. **Test:** Verify all queries work and UI looks professional
6. **Deploy:** Host for presentation to DP World
