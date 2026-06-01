# Document 2 — System Architecture

## 1. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        ENTERPRISE NETWORK                             │
│                                                                       │
│   ┌──────────┐     ┌──────────────────────────────────────────────┐  │
│   │  Browser │────►│              API Gateway                     │  │
│   │Streamlit │     │  FastAPI · JWT Auth · Rate Limit · Audit Log  │  │
│   │  :8501   │     │                  :8000                        │  │
│   └──────────┘     └────────────────────┬─────────────────────────┘  │
│                                         │                             │
│                    ┌────────────────────▼─────────────────────────┐  │
│                    │           LangGraph Pipeline                   │  │
│                    │                                                │  │
│                    │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │  │
│                    │  │ Table    │  │  Value   │  │    SQL     │  │  │
│                    │  │Retrieval │─►│  Mapper  │─►│ Generator  │  │  │
│                    │  │ Mod. 2   │  │  Mod. 3  │  │  Mod. 4   │  │  │
│                    │  └──────────┘  └──────────┘  └─────┬──────┘  │  │
│                    │       ▲                             │         │  │
│                    │       │                             ▼         │  │
│                    │  ┌────┴─────┐               ┌────────────┐   │  │
│                    │  │ Schema   │               │    SQL     │   │  │
│                    │  │Registry  │               │ Validator  │   │  │
│                    │  │  Mod. 1  │               │  Mod. 5   │   │  │
│                    │  └──────────┘               └─────┬──────┘  │  │
│                    │                                   │ (retry)  │  │
│                    │                                   ▼         │  │
│                    │  ┌──────────┐               ┌────────────┐   │  │
│                    │  │  Report  │               │    SQL     │   │  │
│                    │  │Formatter │◄──────────────│  Executor  │   │  │
│                    │  │  Mod. 7  │               │  Mod. 6   │   │  │
│                    │  └──────────┘               └─────┬──────┘  │  │
│                    └────────────────────────────────────┼─────────┘  │
│                                                         │             │
│   ┌──────────────┐     ┌─────────────┐     ┌──────────▼───────────┐  │
│   │  Ollama SLM  │     │  Registry   │     │    Metrics Server    │  │
│   │  :11434      │     │     DB      │     │  (Telecom OSS/BSS)   │  │
│   │  sqlcoder    │     │  SQLite/PG  │     │  SQLite/PostgreSQL   │  │
│   │  mistral     │     │             │     │  READ-ONLY access    │  │
│   └──────────────┘     └─────────────┘     └──────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Request Flow — Step by Step

```
Step  Who         What happens
────  ───────────  ──────────────────────────────────────────────────────
  1   User         Types question: "active customers in Dallas by segment"
  2   Streamlit    HTTP POST /query  with JWT token
  3   API Gateway  Validates JWT, checks rate limit, creates audit record
  4   Module 1     Schema Registry consulted — fetches all table metadata
  5   Module 2     Table Retrieval scores tables (+10/+5/+3/+4 weights)
                   → Selects: customer_accounts, revenue_metrics
  6   Module 3     Value Mapper scans question for known labels
                   → "active" = 'A', "Dallas" = 'DFW'
                   → Builds SQL hint comment block
  7   Module 4     SQL Generator builds prompt:
                     [DDL schema] + [hint block] + [question]
                   → Calls Ollama (sqlcoder model)
                   → Receives: SELECT segment, COUNT(*) FROM customer_accounts
                               WHERE status='A' AND region='DFW' ...
  8   Module 5     SQL Validator checks 5 rules:
                     Rule 1: SELECT only? ✓
                     Rule 2: Tables whitelisted? ✓
                     Rule 3: LIMIT present? ✓
                     Rule 4: Subquery depth ≤ 3? ✓
                     Rule 5: No UNION? ✓
                   If FAIL → retry up to 2× with error feedback to Module 4
  9   Module 6     SQL Executor runs against Metrics Server (read-only)
                   → Returns 3 rows in 1ms
 10   Module 7     Report Formatter builds narrative prompt
                   → Calls Ollama (mistral model)
                   → Returns: Summary + Key Insights + Recommendations
 11   API Gateway  Audit log updated, response returned to Streamlit
 12   Streamlit    Displays: Report · Data Table · SQL · Pipeline details
```

---

## 3. The Three Intelligence Layers

### Layer 1 — Schema Intelligence (Modules 1-3)

The model knows nothing about your database. These modules inject that knowledge:

```
Schema Registry          Table Retriever          Value Mapper
──────────────           ───────────────          ────────────
Stores:                  Scores tables by:        Translates:
• Table names            +10 name match           "Dallas"   → 'DFW'
• Column types           +5  keyword match        "active"   → 'A'
• Descriptions           +3  column match         "critical" → 'P1'
• Internal codes         +4  value label match    "dropped   → '3'
• Human labels                                     call"
                         Returns top 2-3 tables
```

### Layer 2 — Query Intelligence (Modules 4-6)

```
SQL Generator Prompt = DDL Schema + Value Hints + Question

Example prompt sent to Ollama:
┌─────────────────────────────────────────────────────────────┐
│ -- Customer master records                                   │
│ CREATE TABLE customer_accounts (                            │
│     customer_id INTEGER,                                     │
│     status TEXT,    -- A=Active, I=Inactive, S=Suspended    │
│     region TEXT,    -- DFW=Dallas, NYC=New York             │
│     segment TEXT,   -- ENT=Enterprise, SMB=Small Business   │
│     mrr REAL        -- Monthly recurring revenue            │
│ );                                                          │
│                                                             │
│ -- Value alias hints:                                       │
│ -- 'active' → customer_accounts.status = 'A'               │
│ -- 'Dallas' → customer_accounts.region = 'DFW'             │
│                                                             │
│ Question: active customers in Dallas by segment             │
│                                                             │
│ SQL Query:                                                  │
└─────────────────────────────────────────────────────────────┘
```

### Layer 3 — Report Intelligence (Module 7)

```
Raw rows:
  SMB | 24 | $264.80
  CON | 11 | $207.13
  ENT | 10 | $2,036.19

                    ↓  Ollama (mistral)

Report:
  Summary: The DFW region has 45 active customers...
  Key Insights:
    - Enterprise segment generates 89% of MRR despite being only 22% of customers
    - Small Business is the largest segment by count (53%)
  Recommended Actions: Focus retention efforts on ENT segment...
```

---

## 4. LangGraph State Machine

```
                    ┌─────────────────┐
                    │   START         │
                    │  {question}     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ table_retrieval │  Module 2
                    │ selected_tables │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  value_mapper   │  Module 3
                    │ mapping_result  │
                    │   ddl_block     │
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │        sql_generator        │  Module 4 + Ollama
              │       sql_gen_result        │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │        sql_validator        │  Module 5
              │      validation_result      │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │         VALID?              │
              └─────┬──────────────┬────────┘
                    │ YES          │ NO (retry < 2)
                    │              └──► sql_generator (with error feedback)
                    │
              ┌─────▼───────────────┐
              │    sql_executor     │  Module 6 → Metrics DB
              │     exec_result     │
              └─────────┬───────────┘
                        │
              ┌─────────▼───────────┐
              │  report_formatter   │  Module 7 + Ollama
              │       report        │
              └─────────┬───────────┘
                        │
                    ┌───▼────┐
                    │  END   │
                    └────────┘
```

---

## 5. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ INPUT                                                            │
│ "How many active Enterprise customers are in Dallas?"           │
└───────────────────────────────────┬─────────────────────────────┘
                                    │
                    ┌───────────────▼──────────────┐
                    │         TABLE RETRIEVAL       │
                    │  Input:  question tokens      │
                    │  Output: [customer_accounts,  │
                    │           revenue_metrics]    │
                    └───────────────┬──────────────┘
                                    │
                    ┌───────────────▼──────────────┐
                    │          VALUE MAPPER         │
                    │  Input:  question + tables    │
                    │  Output: active   → 'A'       │
                    │          Dallas   → 'DFW'     │
                    │          Enterprise → 'ENT'   │
                    └───────────────┬──────────────┘
                                    │
                    ┌───────────────▼──────────────┐
                    │         SQL GENERATOR         │
                    │  Input:  DDL + hints + Q      │
                    │  LLM:    Ollama sqlcoder       │
                    │  Output: SELECT COUNT(*)      │
                    │          FROM customer_accounts│
                    │          WHERE status='A'     │
                    │          AND region='DFW'     │
                    │          AND segment='ENT'    │
                    │          LIMIT 10000          │
                    └───────────────┬──────────────┘
                                    │
                    ┌───────────────▼──────────────┐
                    │         SQL VALIDATOR         │
                    │  ✓ Rule 1: SELECT only        │
                    │  ✓ Rule 2: customer_accounts  │
                    │             is whitelisted    │
                    │  ✓ Rule 3: LIMIT present      │
                    │  ✓ Rule 4: No deep subqueries │
                    │  ✓ Rule 5: No UNION           │
                    └───────────────┬──────────────┘
                                    │
                    ┌───────────────▼──────────────┐
                    │         SQL EXECUTOR          │
                    │  Connection: read-only pool   │
                    │  Result: [{"count(*)": 10}]   │
                    │  Time: 1.2ms  Rows: 1         │
                    └───────────────┬──────────────┘
                                    │
                    ┌───────────────▼──────────────┐
                    │       REPORT FORMATTER        │
                    │  LLM: Ollama mistral          │
                    │  Output: narrative + table    │
                    │           + insights          │
                    └───────────────┬──────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────┐
│ OUTPUT                                                           │
│ "There are 10 active Enterprise customers in the Dallas (DFW)   │
│  region. This represents 22% of the total DFW active base..."   │
│                                                                  │
│ | count(*) |                                                     │
│ |----------|                                                     │
│ | 10       |                                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Security Layers                          │
│                                                             │
│  Layer 1 — Network                                         │
│    • All traffic stays within enterprise network           │
│    • No outbound internet calls                            │
│    • Ollama bound to localhost only                        │
│                                                             │
│  Layer 2 — Authentication                                  │
│    • JWT tokens (HS256, expire in 60 min)                  │
│    • Every API endpoint requires valid token               │
│    • Role-based: analyst vs admin                          │
│                                                             │
│  Layer 3 — Rate Limiting                                   │
│    • 20 requests/minute per IP                             │
│    • Prevents runaway batch abuse                          │
│                                                             │
│  Layer 4 — SQL Safety                                      │
│    • AST-level parsing (sqlglot)                           │
│    • No INSERT/UPDATE/DELETE/DROP/CREATE/ALTER             │
│    • Only whitelisted tables                               │
│    • Max 10,000 rows per query                             │
│    • Max 30 second execution timeout                       │
│                                                             │
│  Layer 5 — DB Connection                                   │
│    • Read-only SQLite URI (?mode=ro)                       │
│    • Connection-level write block event listener           │
│    • Connection pool with max_overflow limit               │
│                                                             │
│  Layer 6 — Audit                                           │
│    • Every query: user_id, question, SQL, rows, timing     │
│    • Immutable audit log (append-only)                     │
│    • Admin-only access to audit endpoint                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Deployment Architecture

### Single Server (Recommended for most deployments)

```
┌──────────────────────────────────────────┐
│           Enterprise Server              │
│         (8+ GB RAM, GPU optional)        │
│                                          │
│  ┌────────────┐  ┌────────────────────┐  │
│  │  Ollama    │  │   Python App       │  │
│  │ :11434     │  │  FastAPI :8000     │  │
│  │ sqlcoder   │  │  Streamlit :8501   │  │
│  │ mistral    │  │  LangGraph         │  │
│  └────────────┘  └────────────────────┘  │
│                                          │
│  ┌────────────┐  ┌────────────────────┐  │
│  │ Registry   │  │  Metrics DB        │  │
│  │ SQLite     │  │  (your existing    │  │
│  │            │  │   DB server)       │  │
│  └────────────┘  └────────────────────┘  │
└──────────────────────────────────────────┘
```

### Docker Compose (Recommended for production)

```
docker-compose.yml
│
├── tti-ollama  (ollama/ollama image, GPU passthrough)
├── tti-api     (FastAPI app, depends on ollama)
└── tti-ui      (Streamlit app, depends on api)
```
