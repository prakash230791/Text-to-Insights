# Document 6 — Deployment Guide

## Option A — Local Desktop / Laptop (Development)

### Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| RAM | 8 GB | 16 GB |
| Disk | 10 GB free | 20 GB |
| Python | 3.11+ | 3.11+ |
| OS | Windows 10 / macOS 12 / Ubuntu 20 | Latest |
| GPU | Not required | NVIDIA 8GB+ VRAM |

### Step 1 — Install Ollama

**macOS / Windows:** Download from https://ollama.com → run installer

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Verify:
```bash
ollama --version
# ollama version is 0.4.x
```

### Step 2 — Pull Models

```bash
# Best SQL accuracy (7B, ~4GB download)
ollama pull sqlcoder

# Best report quality (7B, ~4GB download)
ollama pull mistral

# Lightweight alternative for low-RAM machines (3.8B, ~2GB)
ollama pull phi3
```

Check models are ready:
```bash
ollama list
# NAME              ID              SIZE    MODIFIED
# sqlcoder:latest   ...             4.1 GB  ...
# mistral:latest    ...             4.1 GB  ...
```

### Step 3 — Clone and Configure

```bash
git clone <your-repo>/Text-to-Insights
cd Text-to-Insights

# Create .env from template
cp .env.example .env

# Edit .env — only these lines matter for local setup:
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_SQL_MODEL=sqlcoder
# OLLAMA_REPORT_MODEL=mistral
# METRICS_DB_URL=sqlite:///./data/telecom_metrics.db
```

### Step 4 — Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 5 — Seed the Database

```bash
# Creates data/registry.db and data/telecom_metrics.db
python -m scripts.seed_telecom
```

### Step 6 — Run

```bash
# Terminal 1 — API
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — UI
streamlit run ui/app.py

# Open in browser
# API docs: http://localhost:8000/docs
# UI:       http://localhost:8501
```

---

## Option B — Docker Compose (Recommended for Production)

### Prerequisites

- Docker 24+
- Docker Compose v2
- NVIDIA GPU + nvidia-container-toolkit (optional but recommended)

### Step 1 — Configure

```bash
cp .env.example .env
# Edit .env with your metrics DB credentials
```

### Step 2 — Build and Run

```bash
# Build and start all services
docker compose up -d

# Pull Ollama models (first run only)
docker exec tti-ollama ollama pull sqlcoder
docker exec tti-ollama ollama pull mistral

# Check all services are healthy
docker compose ps
```

### Step 3 — Seed the Database

```bash
docker exec tti-api python -m scripts.seed_telecom
```

### Service URLs

| Service | URL |
|---------|-----|
| API | http://your-server:8000 |
| API Docs | http://your-server:8000/docs |
| Streamlit UI | http://your-server:8501 |
| Ollama | http://localhost:11434 (internal only) |

### docker-compose.yml services

```
tti-ollama  — Ollama model server (GPU passthrough if available)
tti-api     — FastAPI application
tti-ui      — Streamlit frontend
```

---

## Option C — Connecting to Your Real Metrics DB

By default the system uses a local SQLite test database. To connect to your actual telecom metrics server:

### PostgreSQL

```bash
# .env
METRICS_DB_URL=postgresql://readonly_user:password@metrics-server:5432/telecom_db
METRICS_DB_POOL_SIZE=10
METRICS_DB_MAX_OVERFLOW=20
```

```bash
# Install PostgreSQL driver
pip install psycopg2-binary
```

### Microsoft SQL Server

```bash
# .env
METRICS_DB_URL=mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server
```

```bash
pip install pyodbc
```

### Oracle

```bash
METRICS_DB_URL=oracle+cx_oracle://user:pass@host:1521/service_name
pip install cx_Oracle
```

> **Important:** Always use a **read-only** database account. The SQL Executor also enforces read-only at the application layer, but defence-in-depth is best practice.

---

## Step 4 — Run the Auto-Scanner

After connecting to your real database, run the auto-scanner to populate the registry:

```bash
python -m registry.auto_scanner
```

This will:
1. Discover all tables and columns
2. Sample distinct values for low-cardinality columns
3. Flag unknown values for data-team curation
4. Log all activity to `registry_audit`

Then **manually curate** the flagged values via the Schema Browser in the UI, or directly in the registry DB:

```sql
UPDATE registry_values
SET human_label = 'Active Customer',
    is_manually_curated = 1,
    is_flagged_unknown = 0
WHERE table_name = 'your_table'
  AND column_name = 'status'
  AND internal_code = 'A';
```

---

## Nightly Delta Detection (Cron)

Set up a cron job to detect schema changes overnight:

```bash
# crontab -e
0 2 * * * cd /path/to/Text-to-Insights && python -m registry.delta_detector >> /var/log/tti-delta.log 2>&1
```

Configure the alert email in `.env`:
```bash
ALERT_EMAIL_TO=data-team@telecom.internal
SMTP_HOST=mail.telecom.internal
SMTP_PORT=25
```

---

## Production Checklist

```
Security
  □ Change JWT_SECRET_KEY to a strong random value (min 32 chars)
  □ Set APP_ENV=production
  □ Use HTTPS (nginx reverse proxy with TLS certificate)
  □ Restrict Ollama to localhost only (not exposed externally)
  □ Use a read-only DB user for METRICS_DB_URL

Performance
  □ Use GPU server for Ollama (10x faster than CPU)
  □ Increase METRICS_DB_POOL_SIZE for high concurrency
  □ Pin Ollama model versions (use digest tags, not :latest)

Operations
  □ Set up cron for delta_detector (nightly at 2am)
  □ Configure SMTP for alert emails
  □ Set up log rotation for uvicorn logs
  □ Monitor /health endpoint with your standard monitoring tool
  □ Back up data/registry.db regularly (it contains your curated mappings)
```

---

## Hardware Sizing Guide

| Users | Queries/day | Recommended Hardware |
|-------|------------|---------------------|
| 1-5 | < 50 | Any laptop with 8GB RAM |
| 5-20 | 50-500 | Server with NVIDIA RTX 3090/4090 (24GB VRAM) |
| 20-100 | 500-5000 | Server with A100/H100 or 2× RTX 4090 |
| 100+ | 5000+ | Kubernetes cluster, multiple Ollama replicas |
