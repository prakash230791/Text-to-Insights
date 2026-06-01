# Text-to-Insights — Documentation Index

> Enterprise Natural Language Query System for Telecom OSS/BSS Metrics  
> **100% On-Premise · Zero External API Cost · Local AI via Ollama**

---

## Documents

| # | Document | Description |
|---|----------|-------------|
| 1 | [Project Overview](01_project_overview.md) | What it is, the problem it solves, business value |
| 2 | [System Architecture](02_system_architecture.md) | Full architecture, pipeline flow, data flow diagrams |
| 3 | [Module Reference](03_module_reference.md) | Deep-dive into all 8 modules with code examples |
| 4 | [Data Model](04_data_model.md) | Schema Registry tables, telecom data model, value mappings |
| 5 | [API Reference](05_api_reference.md) | All REST endpoints with request/response examples |
| 6 | [Deployment Guide](06_deployment_guide.md) | Local setup, Docker, production deployment |
| 7 | [Presentation](presentation.html) | Executive slide deck (open in browser) |
| 8 | [Architecture Diagram](architecture.png) | Visual pipeline diagram (generated) |

---

## Quick Start

```bash
# 1. Install Ollama and pull models
curl -fsSL https://ollama.com/install.sh | sh
ollama pull sqlcoder && ollama pull mistral

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Seed the database
python -m scripts.seed_telecom

# 4. Start the API
uvicorn api.main:app --reload

# 5. Start the UI
streamlit run ui/app.py
```

**API:** http://localhost:8000/docs  
**UI:** http://localhost:8501  
**Demo credentials:** `analyst / analyst123`

---

## Architecture at a Glance

```
User Question (plain English)
         │
         ▼
  ┌─────────────┐
  │ API Gateway │  JWT auth · Rate limiting · Audit logging
  └──────┬──────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │                  LangGraph Pipeline                  │
  │                                                      │
  │  Schema      Table       Value      SQL              │
  │  Registry ─► Retrieval ─► Mapper ─► Generator       │
  │  (Module 1)  (Module 2)  (Module 3) (Module 4)      │
  │                                        │  Ollama     │
  │                              SQL Validator           │
  │                              (Module 5)              │
  │                                  │                   │
  │                            SQL Executor              │
  │                            (Module 6) ──► Metrics DB │
  │                                  │                   │
  │                          Report Formatter            │
  │                          (Module 7) ──► Ollama       │
  └─────────────────────────────────────────────────────┘
         │
         ▼
  Narrative Report + Data Table + Key Insights
```
