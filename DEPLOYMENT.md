# DP World Maritime FP&A Chatbot - Deployment Guide

## Application Ready

The Financial Chatbot has been deployed and is ready for testing.

## To Run

1. **Start the server:**
```bash
cd c:/Users/NISHKA/Downloads/Financial_chatbot_dp_world
python main.py
```

Server runs on: `http://localhost:5001`

## Testing

### Test via cURL (POST request):
```bash
curl -X POST http://localhost:5001/api/query \
  -H "Content-Type: application/json" \
  -d '{"message":"Which vessel has the highest crew cost to revenue ratio?","unit":"Africa"}'
```

### Test via Python:
```python
import requests
response = requests.post(
    'http://localhost:5001/api/query',
    json={'message': 'Show crew costs by vessel', 'unit': 'Africa'}
)
print(response.json())
```

## Query Types Supported

- **Simple queries** (fast): Crew breakdown, top costs, revenue, by vessel
- **Complex queries** (LLM-powered): Ratios, percentages, comparisons, analysis

## API Response Format

```json
{
  "success": true,
  "query": "user's original question",
  "answer": "LLM-generated narrative answer",
  "data": [...],
  "metadata": {
    "sql_query": "...",
    "columns_returned": [...],
    "execution_time_ms": 51,
    "total_rows": 1
  },
  "download": {
    "csv": "...",
    "json": [...]
  }
}
```

## Available Endpoints

- `POST /api/query` - Main query endpoint
- `GET /api/units` - List units
- `GET /api/vessels?unit=Africa` - List vessels
- `GET /api/schema` - Database schema
- `GET /api/health` - Health check
- `GET /` - Frontend (if available)

## Architecture

1. **QueryGenerator**: Routes simple queries → direct SQL
2. **LLMService**: Routes complex queries → LLM generates SQL
3. **DatabaseService**: Validates and executes SQL
4. **CalculatorService**: Executes queries and formats results
5. **Main API**: Orchestrates flow, generates narrative answers

All components tested and working.
