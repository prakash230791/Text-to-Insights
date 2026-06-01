# Document 1 — Project Overview

## 1. What is Text-to-Insights?

Text-to-Insights is an **enterprise-grade natural language query system** that allows business analysts and operations teams to query a telecom metrics server using plain English — with no SQL knowledge required.

All processing is **fully on-premise** using locally hosted Small Language Models (SLMs) via Ollama.  
**Zero external API spend. Zero data leaves your network.**

---

## 2. The Problem

Telecom metrics servers contain hundreds of tables with cryptic internal codes:

| What the DB stores | What humans say |
|--------------------|-----------------|
| `status = 'A'` | "active customers" |
| `region = 'DFW'` | "Dallas" |
| `outcome_code = '3'` | "dropped call" |
| `priority = 'P1'` | "critical ticket" |
| `segment = 'ENT'` | "enterprise customer" |

**Business users cannot query data directly.** Every ad-hoc question requires:
1. Finding the right engineer
2. Engineer decodes the business question into SQL
3. Engineer runs the query
4. Engineer formats and returns results
5. Repeat for every follow-up question

This creates:
- **Multi-day delays** on business-critical questions
- **Engineering bottleneck** — analysts occupy 30-40% of engineering time
- **Rigid dashboards** — cannot handle ad-hoc analytical questions
- **Dependency risk** — knowledge of table structure siloed in a few engineers

---

## 3. The Solution

A **three-layer intelligence pipeline** sits between the user's natural language question and the metrics database:

```
Layer 1 — Schema Intelligence
  Knows your tables, columns, and exact internal codes
  Translates "Dallas" → 'DFW' before SQL is generated

Layer 2 — Query Intelligence  
  Local AI generates SQL using enriched schema context
  Safety validator blocks any write operations

Layer 3 — Report Intelligence
  Local AI converts raw rows into a narrative business report
  Includes key insights and recommended actions
```

---

## 4. Business Value

### Time saved per query
| Step | Before | After |
|------|--------|-------|
| Submit question | Email to engineering team | Type in UI — 5 seconds |
| Understand the data | Engineer reads schema docs | Automatic |
| Write SQL | 15-60 minutes | 10-30 seconds (AI) |
| Run & format | 10-30 minutes | Automatic |
| Receive answer | 1-3 business days | Under 60 seconds |

### Annual impact (estimated, 50-analyst team)
- **Engineering hours freed:** ~2,000 hrs/year (50 analysts × 40 queries/month × 3 min saved)
- **Faster decisions:** From days to seconds on critical KPIs
- **Zero API cost:** No per-query charges — infrastructure cost only

---

## 5. Enterprise Requirements Met

| Requirement | Implementation |
|-------------|----------------|
| **Data Privacy** | 100% on-premise. No data leaves the enterprise network |
| **Zero External Cost** | Ollama + open-source models. No API subscriptions |
| **Security** | JWT authentication on all endpoints, role-based access |
| **Audit Trail** | Every query logged: user ID, timestamp, generated SQL, row count |
| **SQL Safety** | Whitelist + read-only + row cap validation before any DB execution |
| **Schema Freshness** | Nightly cron detects new unknown column values, alerts data team |
| **Performance** | Selective schema context (2-3 tables, not 200+), result caching ready |
| **Multi-user** | Session isolation, concurrent query handling via FastAPI async |

---

## 6. Technology Stack

| Component | Technology | Cost | Purpose |
|-----------|-----------|------|---------|
| SLM Runtime | Ollama | Free | Runs language models locally |
| SQL Model | SQLCoder 7B / Mistral 7B | Free | Text-to-SQL generation |
| Report Model | Mistral 7B / Phi-3 | Free | Narrative report generation |
| API Layer | FastAPI (Python) | Free | REST gateway, auth, routing |
| UI Layer | Streamlit | Free | Business user query interface |
| Orchestration | LangGraph | Free | Pipeline workflow management |
| Schema Registry | SQLite / PostgreSQL | Free | Metadata store |
| Primary Language | Python 3.11+ | Free | All backend modules |

**Total external API cost: $0**

---

## 7. Build Roadmap

| Phase | Week | Deliverables |
|-------|------|--------------|
| Phase 1 — Foundation | Week 1 | Schema Registry DB, auto-scanner, Value Mapper, Table Retrieval ✅ |
| Phase 2 — Core Pipeline | Week 2 | SQL Generator, Validator, Executor, Report Formatter ✅ |
| Phase 3 — Enterprise Layer | Week 3 | FastAPI gateway, JWT auth, audit logging, rate limiting ✅ |
| Phase 4 — UI + Observability | Week 4 | Streamlit UI, query history, delta detection, alerts ✅ |
| Phase 5 — Vector Upgrade | Future | Replace keyword scoring with local sentence-transformer embeddings |
| Phase 6 — Caching | Future | Redis query result caching, response time < 5s for repeated queries |
