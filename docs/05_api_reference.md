# Document 5 — API Reference

**Base URL:** `http://localhost:8000`  
**Interactive Docs:** http://localhost:8000/docs  
**Auth:** Bearer JWT (obtain from `POST /auth/token`)

---

## POST /auth/token

Exchange username and password for a JWT access token.

**No authentication required.**

### Request

```
Content-Type: application/x-www-form-urlencoded

username=analyst&password=analyst123
```

### Response 200

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### cURL Example

```bash
curl -X POST http://localhost:8000/auth/token \
  -d "username=analyst&password=analyst123"
```

---

## POST /query

Submit a natural language question. Runs the full 8-module pipeline.

**Requires:** Analyst or Admin role.

### Request Body

```json
{
  "question": "How many active customers are in the Dallas region by segment?",
  "domain": "customer",
  "top_k_tables": 3,
  "allow_set_operations": false
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `question` | string | ✅ | — | Natural language question (5-1000 chars) |
| `domain` | string | ❌ | null | Filter table retrieval to a domain |
| `top_k_tables` | integer | ❌ | 3 | Tables to retrieve (1-5) |
| `allow_set_operations` | boolean | ❌ | false | Allow UNION/INTERSECT in SQL |

### Response 200

```json
{
  "query_id": "q_ab12cd34ef56",
  "question": "How many active customers are in Dallas by segment?",
  "selected_tables": ["customer_accounts", "revenue_metrics"],
  "value_mappings": [
    {
      "original_phrase": "active",
      "internal_code": "A",
      "table_name": "customer_accounts",
      "column_name": "status"
    },
    {
      "original_phrase": "Dallas",
      "internal_code": "DFW",
      "table_name": "customer_accounts",
      "column_name": "region"
    }
  ],
  "generated_sql": "SELECT segment, COUNT(*) as count, ROUND(AVG(mrr),2) as avg_mrr FROM customer_accounts WHERE status='A' AND region='DFW' GROUP BY segment ORDER BY count DESC LIMIT 10000",
  "validation_warnings": [],
  "row_count": 3,
  "execution_time_ms": 1.2,
  "truncated": false,
  "report": "**Summary**: The DFW region has 45 active customers distributed across three segments...\n\n**Key Insights**:\n- Enterprise customers generate 89% of total MRR\n...\n\n---\n\n| segment | count | avg_mrr |\n|---|---|---|\n| SMB | 24 | 264.8 |",
  "markdown_table": "| segment | count | avg_mrr |\n|---|---|---|\n| SMB | 24 | 264.8 |\n| CON | 11 | 207.13 |\n| ENT | 10 | 2036.19 |"
}
```

### Response 422 — Validation Error

```json
{
  "detail": "SQL validation failed: Rule 2 violation: table 'system_logs' is not in the approved table whitelist."
}
```

### Response 429 — Rate Limit

```json
{
  "detail": "Rate limit exceeded. Max 20 requests/minute."
}
```

### cURL Example

```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X POST http://localhost:8000/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "How many active customers are in Dallas by segment?"}'
```

---

## GET /query/history

Retrieve past queries for the authenticated user (paginated).

**Requires:** Analyst or Admin role.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number |
| `page_size` | integer | 20 | Records per page (max 100) |

### Response 200

```json
{
  "total": 47,
  "page": 1,
  "page_size": 20,
  "records": [
    {
      "query_id": "q_ab12cd34ef56",
      "question": "How many active customers are in Dallas?",
      "status": "SUCCESS",
      "row_count": 3,
      "created_at": "2024-12-01T10:32:15"
    }
  ]
}
```

---

## GET /schema/tables

Browse all registered tables and their column metadata.

**Requires:** Analyst or Admin role.

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `domain` | string | Filter by domain: `customer`, `network`, `billing` |

### Response 200

```json
{
  "tables": [
    {
      "table_name": "customer_accounts",
      "description": "Customer master records including status, segment, and market region",
      "domain": "customer",
      "keywords": "customer account subscriber segment region market",
      "column_count": 8,
      "columns": [
        {
          "name": "status",
          "type": "TEXT",
          "description": "Account status code: A=Active, I=Inactive, S=Suspended",
          "is_metric": false,
          "is_dimension": true
        }
      ]
    }
  ],
  "total": 8
}
```

---

## GET /schema/values/{table_name}

View all curated value mappings for a specific table.

**Requires:** Analyst or Admin role.

### Path Parameters

| Parameter | Description |
|-----------|-------------|
| `table_name` | Exact table name as registered |

### Query Parameters

| Parameter | Description |
|-----------|-------------|
| `column_name` | Filter to a specific column |

### Response 200

```json
{
  "table_name": "customer_accounts",
  "curated_values": [
    {"column_name": "status",  "internal_code": "A",   "human_label": "Active"},
    {"column_name": "status",  "internal_code": "I",   "human_label": "Inactive"},
    {"column_name": "region",  "internal_code": "DFW", "human_label": "Dallas"},
    {"column_name": "segment", "internal_code": "ENT", "human_label": "Enterprise"}
  ],
  "flagged_unknown": []
}
```

### Response 404

```json
{
  "detail": "Table 'xyz' not found in the Schema Registry"
}
```

---

## GET /audit/log

Full audit trail with user, SQL, row count, and timing.

**Requires:** Admin role only.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_id` | string | null | Filter to specific user |
| `page` | integer | 1 | Page number |
| `page_size` | integer | 50 | Records per page |

### Response 200

```json
{
  "total": 1203,
  "page": 1,
  "page_size": 50,
  "records": [
    {
      "id": 1,
      "query_id": "q_ab12cd34ef56",
      "user_id": "analyst",
      "question": "How many active customers are in Dallas?",
      "selected_tables": ["customer_accounts"],
      "generated_sql": "SELECT COUNT(*) FROM customer_accounts WHERE status='A' AND region='DFW' LIMIT 10000",
      "row_count": 1,
      "execution_time_ms": 1,
      "status": "SUCCESS",
      "error_message": "",
      "created_at": "2024-12-01T10:32:15"
    }
  ]
}
```

---

## GET /health

System health check — returns status of all components.

**No authentication required.**

### Response 200 (all healthy)

```json
{
  "status": "ok",
  "components": {
    "registry_db": "ok",
    "metrics_db": "ok",
    "ollama": {
      "status": "ok",
      "available_models": ["sqlcoder:latest", "mistral:latest"],
      "sql_model_ready": true,
      "report_model_ready": true
    }
  }
}
```

### Response 200 (degraded — Ollama not running)

```json
{
  "status": "degraded",
  "components": {
    "registry_db": "ok",
    "metrics_db": "ok",
    "ollama": "error: Failed to connect to Ollama. Please check that Ollama is running."
  }
}
```

---

## Error Response Format

All errors follow this structure:

```json
{
  "detail": "Human-readable error message"
}
```

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (pipeline error, validation failure) |
| 401 | Unauthorized (missing or expired JWT) |
| 403 | Forbidden (insufficient role) |
| 404 | Resource not found |
| 422 | SQL validation failed |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
