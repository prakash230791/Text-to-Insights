# Document 3 — Module Reference

## Module 1 — Schema Registry

**File:** `registry/schema_db.py`  
**Purpose:** Metadata database that describes every table, column, and value alias in the metrics server.

### Database Tables

| Table | Purpose |
|-------|---------|
| `registry_tables` | One row per queryable table: name, description, domain, keywords |
| `registry_columns` | One row per column: table, column name, type, is_filterable flag |
| `registry_values` | One row per distinct value: internal_code ↔ human_label |
| `registry_audit` | Change log: every add, modify, or flag event |

### Key Design Decisions

- **Never overwrites manually curated labels** — auto-scanner adds new entries but does not touch human-edited ones
- **`is_manually_curated` flag** — distinguishes data-team labels from auto-discovered ones
- **`is_flagged_unknown` flag** — new values discovered by the scanner that need curation

### Supporting Scripts

| Script | Purpose | When to run |
|--------|---------|-------------|
| `registry/auto_scanner.py` | Discovers tables/columns/values from live metrics DB | First setup |
| `registry/delta_detector.py` | Finds new values since last scan | Nightly cron |
| `registry/alert_service.py` | Emails data team about unknown values | Called by delta detector |

### Usage Example

```python
from registry.schema_db import SchemaDB

db = SchemaDB("sqlite:///./data/registry.db")
db.init_db()

# Register a table
db.upsert_table("customer_accounts", 
    description="Customer master records",
    keywords="customer account subscriber region market",
    domain="customer")

# Register a value mapping
db.upsert_value("customer_accounts", "status", "A", "Active")
db.upsert_value("customer_accounts", "region", "DFW", "Dallas")

# Get full table metadata (used by pipeline)
meta = db.get_table_meta("customer_accounts")
print(meta.columns)   # list of ColumnMeta
print(meta.values)    # list of ValueMeta

# Build DDL for LLM prompt
ddl = db.build_ddl_block(["customer_accounts", "trouble_tickets"])
```

---

## Module 2 — Table Retriever

**File:** `core/table_retriever.py`  
**Purpose:** Scores all registered tables against the user question and returns the top 2-3 most relevant.

### Scoring Algorithm

| Signal | Score | Example |
|--------|-------|---------|
| Table name token in query | **+10** | "orders" in query → `orders` table |
| Table keyword match | **+5** | Table tagged "billing" → matches "invoice" query |
| Column name in query | **+3** | "region" column → "Dallas region" query |
| Value human_label in query | **+4** | "Active" label → "active customers" query |

### Phase 2 Upgrade Path

Replace keyword scoring with **local sentence-transformer embeddings** to handle synonyms and paraphrasing. The `retrieve()` method signature stays the same — only the scoring internals change.

### Usage Example

```python
from core.table_retriever import TableRetriever

retriever = TableRetriever(db, top_k=3)
retriever.refresh()   # loads all tables from registry

tables = retriever.retrieve("active customers in Dallas by segment")
# Returns: [TableMeta(customer_accounts), TableMeta(revenue_metrics), ...]

# retrieve_with_meta() — same but ensures columns+values populated
tables = retriever.retrieve_with_meta("dropped calls in DFW last week")
for t in tables:
    print(t.table_name, [c.column_name for c in t.columns])
```

---

## Module 3 — Value Mapper

**File:** `core/value_mapper.py`  
**Purpose:** Translates plain-language terms in the question to exact internal DB codes before SQL generation.

### How It Works

1. Loads all curated `registry_values` (human_label → internal_code)
2. Sorts by phrase length (longest first — "Small Business" wins over "Business")
3. Scans the question using word-boundary regex
4. Returns matched mappings + SQL comment hint block

### Usage Example

```python
from core.value_mapper import ValueMapper

mapper = ValueMapper(db)
mapper.refresh()

result = mapper.map(
    "Show active Enterprise customers in Dallas with critical tickets",
    table_names=["customer_accounts", "trouble_tickets"]
)

print(result.mappings)
# [MappedValue(original='active',     internal_code='A',   table='customer_accounts', col='status'),
#  MappedValue(original='Enterprise', internal_code='ENT', table='customer_accounts', col='segment'),
#  MappedValue(original='Dallas',     internal_code='DFW', table='customer_accounts', col='region'),
#  MappedValue(original='critical',   internal_code='P1',  table='trouble_tickets',   col='priority')]

print(result.as_hint_block())
# -- Value alias hints (use these exact values in WHERE clauses):
# --   'active'     → customer_accounts.status  = 'A'
# --   'Enterprise' → customer_accounts.segment = 'ENT'
# --   'Dallas'     → customer_accounts.region  = 'DFW'
# --   'critical'   → trouble_tickets.priority  = 'P1'
```

---

## Module 4 — SQL Generator

**File:** `core/sql_generator.py`  
**Purpose:** Calls a locally hosted SLM via Ollama to convert the enriched prompt into valid SQL.

### Recommended Models

| Model | Size | Best For | RAM |
|-------|------|---------|-----|
| `sqlcoder` (Defog) | 7B | Highest SQL accuracy | 8GB+ |
| `mistral` | 7B | Best general quality | 8GB+ |
| `phi3` | 3.8B | Fastest, CPU-only | 4GB+ |

### Prompt Template

```
### Task
Generate a SQL SELECT query that answers the question below.
Use only the tables and columns defined in the schema.
Apply every value alias hint exactly as specified.
Always add LIMIT {row_limit} unless the query already has one.
Output only the SQL query — no explanations, no markdown fences.

### Database Schema
{ddl_block}

### Value Alias Hints
{hint_block}

### Question
{question}

### SQL Query
```

### Usage Example

```python
from core.sql_generator import SQLGenerator

gen = SQLGenerator()
result = gen.generate(
    question="How many active customers are in Dallas?",
    ddl_block="CREATE TABLE customer_accounts (...);",
    hint_block="-- 'active' → customer_accounts.status = 'A'\n-- 'Dallas' → customer_accounts.region = 'DFW'"
)
print(result.sql)
# SELECT COUNT(*) FROM customer_accounts WHERE status='A' AND region='DFW' LIMIT 10000
```

---

## Module 5 — SQL Validator

**File:** `core/sql_validator.py`  
**Purpose:** Rule-based safety layer that runs BEFORE executing any generated SQL.

### Validation Rules

| Rule | Check | On Failure |
|------|-------|------------|
| Rule 1 | SELECT only — no INSERT/UPDATE/DELETE/DROP/CREATE/ALTER | Reject |
| Rule 2 | Only whitelisted tables (from `config/table_whitelist.py`) | Reject |
| Rule 3 | LIMIT ≤ 10,000 rows. Auto-inject if missing | Inject or reject |
| Rule 4 | No subquery depth beyond 3 levels | Reject |
| Rule 5 | No UNION/INTERSECT/EXCEPT without approval flag | Reject |
| Rule 6 | Execution time limit (30s) | Enforced by executor |

### Retry Loop

If validation fails, the pipeline sends the error message back to the SQL Generator as context:

```
[Previous attempt failed validation: Rule 2 violation: table 'secret_data' 
 is not in the approved table whitelist. Please fix the SQL.]
```

The generator gets 2 retry attempts before the pipeline terminates with an error.

### Usage Example

```python
from core.sql_validator import SQLValidator

validator = SQLValidator()
result = validator.validate("SELECT * FROM customer_accounts LIMIT 100")

print(result.is_valid)    # True
print(result.warnings)    # []
print(result.sql)         # "SELECT * FROM customer_accounts LIMIT 100"

# Test a dangerous query
result = validator.validate("DROP TABLE customer_accounts")
print(result.is_valid)    # False
print(result.errors)      # ["Rule 1 violation: write operation not permitted..."]
```

---

## Module 6 — SQL Executor

**File:** `core/sql_executor.py`  
**Purpose:** Executes validated SQL against the metrics server using a read-only connection pool.

### Safety Features

- **SQLite read-only URI:** `sqlite:///file:path?mode=ro&uri=true`
- **Connection event hook:** Blocks any write statement at the driver level
- **Connection pool:** Configurable size, prevents connection exhaustion
- **Row cap:** Returns max 10,000 rows (configurable)
- **Truncation flag:** `exec_result.truncated = True` if results were capped

### Usage Example

```python
from core.sql_executor import SQLExecutor

executor = SQLExecutor()
result = executor.execute(
    "SELECT segment, COUNT(*) FROM customer_accounts WHERE status='A' GROUP BY segment LIMIT 100"
)

print(result.columns)         # ['segment', 'count(*)']
print(result.rows)            # [{'segment': 'ENT', 'count(*)': 10}, ...]
print(result.row_count)       # 3
print(result.execution_time_ms)  # 1.2
print(result.truncated)       # False
```

---

## Module 7 — Report Formatter

**File:** `core/report_formatter.py`  
**Purpose:** Converts raw SQL result rows into a human-readable business report via a second Ollama call.

### Report Structure

Every report contains:
1. **Summary** — One paragraph explaining the data in plain English
2. **Key Insights** — 3 specific numbered findings from the data
3. **Recommended Actions** — 1-2 business action items

### Usage Example

```python
from core.report_formatter import ReportFormatter

formatter = ReportFormatter()
report = formatter.format(
    question="How many active customers are in DFW by segment?",
    exec_result=exec_result
)

print(report.narrative)      # Full AI-generated narrative
print(report.markdown_table) # Markdown table of raw data
print(report.full_report)    # narrative + "---" + table
```

---

## Module 8 — API Gateway

**Files:** `api/main.py`, `api/auth.py`, `api/routes/`, `api/middleware/`  
**Purpose:** FastAPI application that serves as the entry point for all queries.

### Endpoints Summary

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/token` | None | Exchange credentials for JWT |
| POST | `/query` | Analyst+ | Submit natural language query |
| GET | `/query/history` | Analyst+ | Past queries for current user |
| GET | `/schema/tables` | Analyst+ | Browse registered tables |
| GET | `/schema/values/{table}` | Analyst+ | Value mappings for a table |
| GET | `/audit/log` | Admin only | Full audit trail |
| GET | `/health` | None | System health check |

### Interactive API Docs

When running locally: **http://localhost:8000/docs**
