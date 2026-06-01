# Document 4 — Data Model

## 1. Schema Registry Database

The registry is a dedicated SQLite (or PostgreSQL) metadata database separate from the metrics server.

### registry_tables

```sql
CREATE TABLE registry_tables (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT UNIQUE NOT NULL,        -- exact name in metrics DB
    description TEXT NOT NULL DEFAULT '',   -- human-readable description
    domain      TEXT NOT NULL DEFAULT 'general',  -- customer|network|billing|auto
    keywords    TEXT NOT NULL DEFAULT '',   -- space-separated retrieval keywords
    is_active   BOOLEAN NOT NULL DEFAULT 1, -- soft-delete flag
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### registry_columns

```sql
CREATE TABLE registry_columns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name    TEXT NOT NULL REFERENCES registry_tables(table_name),
    column_name   TEXT NOT NULL,
    data_type     TEXT NOT NULL DEFAULT 'TEXT',
    description   TEXT NOT NULL DEFAULT '',
    is_filterable BOOLEAN DEFAULT 1,   -- eligible for WHERE clauses
    is_metric     BOOLEAN DEFAULT 0,   -- numeric KPI (SUM/AVG applicable)
    is_dimension  BOOLEAN DEFAULT 0,   -- categorical (GROUP BY applicable)
    is_nullable   BOOLEAN DEFAULT 1,
    sample_values TEXT NOT NULL DEFAULT '',
    UNIQUE (table_name, column_name)
);
```

### registry_values

```sql
CREATE TABLE registry_values (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name          TEXT NOT NULL REFERENCES registry_tables(table_name),
    column_name         TEXT NOT NULL,
    internal_code       TEXT NOT NULL,    -- exact value in the metrics DB
    human_label         TEXT NOT NULL,    -- what users call it
    is_manually_curated BOOLEAN DEFAULT 0,  -- True = data team has reviewed
    is_flagged_unknown  BOOLEAN DEFAULT 0,  -- True = needs curation
    UNIQUE (table_name, column_name, internal_code)
);
```

### registry_audit

```sql
CREATE TABLE registry_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,   -- ADDED | MODIFIED | FLAGGED
    entity_type TEXT NOT NULL,   -- TABLE | COLUMN | VALUE
    table_name  TEXT NOT NULL,
    column_name TEXT NOT NULL DEFAULT '',
    old_value   TEXT NOT NULL DEFAULT '',
    new_value   TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 2. Telecom Metrics Schema (Seeded)

### customer_accounts

| Column | Type | Description | Code Examples |
|--------|------|-------------|---------------|
| customer_id | INTEGER | Unique customer ID | — |
| name | TEXT | Customer/company name | — |
| status | TEXT | Account status | A=Active, I=Inactive, S=Suspended |
| segment | TEXT | Customer segment | ENT=Enterprise, SMB=Small Business, CON=Consumer |
| region | TEXT | Market region | DFW=Dallas, NYC=New York, LAX=Los Angeles |
| mrr | REAL | Monthly recurring revenue (USD) | — |
| created_date | DATE | Account creation date | — |
| account_manager | TEXT | Assigned AM | — |

### service_subscriptions

| Column | Type | Description | Code Examples |
|--------|------|-------------|---------------|
| subscription_id | INTEGER | Unique subscription ID | — |
| customer_id | INTEGER | FK to customer_accounts | — |
| service_type | TEXT | Type of service | FIBER, WIRELESS, VOICE, DATA, TV |
| plan_name | TEXT | Commercial plan name | — |
| status | TEXT | Subscription status | A=Active, C=Cancelled, P=Paused |
| monthly_charge | REAL | Monthly charge (USD) | — |
| start_date | DATE | Subscription start | — |
| end_date | DATE | End date (null if active) | — |

### network_kpis

| Column | Type | Description | Code Examples |
|--------|------|-------------|---------------|
| kpi_date | DATE | Measurement date | — |
| region | TEXT | Market region | DFW, NYC, LAX, CHI, HOU, ATL |
| node_id | TEXT | Network node | N1, N2, N3 |
| metric_name | TEXT | KPI type | UPTIME, LATENCY_MS, THROUGHPUT_MBPS, PACKET_LOSS_PCT |
| metric_value | REAL | Measured value | — |
| threshold | REAL | Target threshold | — |
| is_breached | INTEGER | 1 = threshold violated | 0 or 1 |

### trouble_tickets

| Column | Type | Description | Code Examples |
|--------|------|-------------|---------------|
| ticket_id | INTEGER | Unique ticket ID | — |
| customer_id | INTEGER | FK to customer_accounts | — |
| category | TEXT | Issue category | OUTAGE, BILLING, SPEED, EQUIPMENT, OTHER |
| priority | TEXT | Priority level | P1=Critical, P2=High, P3=Normal, P4=Low |
| status | TEXT | Ticket status | O=Open, IP=In Progress, R=Resolved, C=Closed |
| region | TEXT | Region code | — |
| created_at | DATETIME | Ticket created | — |
| resolved_at | DATETIME | Ticket resolved (null if open) | — |
| resolution_hours | REAL | Hours to resolve | — |

### revenue_metrics

| Column | Type | Description |
|--------|------|-------------|
| metric_month | DATE | First day of reporting month |
| region | TEXT | Market region code |
| product_line | TEXT | FIBER, WIRELESS, VOICE |
| total_revenue | REAL | Total revenue (USD) |
| arpu | REAL | Average revenue per user (USD) |
| subscriber_count | INTEGER | Active subscribers at month end |
| churn_rate_pct | REAL | Churn rate % for the period |

### call_logs

| Column | Type | Description | Code Examples |
|--------|------|-------------|---------------|
| call_id | INTEGER | Unique call ID | — |
| customer_id | INTEGER | FK to customer_accounts | — |
| call_date | DATE | Date of call | — |
| region | TEXT | Call origin region | — |
| node_id | TEXT | Handling network node | — |
| outcome_code | TEXT | Call result | 1=Completed, 2=Busy, 3=Dropped, 4=No Answer |
| duration_sec | INTEGER | Duration in seconds | — |

### churn_events

| Column | Type | Description | Code Examples |
|--------|------|-------------|---------------|
| event_id | INTEGER | Unique event ID | — |
| customer_id | INTEGER | FK to customer_accounts | — |
| churn_date | DATE | Date of churn | — |
| reason_code | TEXT | Churn reason | PRICE, COVERAGE, SERVICE, COMPETITOR, MOVED |
| region | TEXT | Customer region | — |
| lifetime_value | REAL | LTV at churn (USD) | — |
| tenure_months | INTEGER | Months as customer | — |

### orders

| Column | Type | Description | Code Examples |
|--------|------|-------------|---------------|
| order_id | INTEGER | Unique order ID | — |
| customer_id | INTEGER | FK to customer_accounts | — |
| order_date | DATE | Order date | — |
| order_type | TEXT | Type of order | NEW, UPGRADE, DOWNGRADE, CANCEL |
| status | TEXT | Order status | A=Active, C=Cancelled, P=Pending, F=Fulfilled |
| region | TEXT | Customer region | — |
| product_line | TEXT | Product ordered | FIBER, WIRELESS, VOICE |
| order_value | REAL | Order value (USD) | — |

---

## 3. Complete Value Mapping Reference

```
Table: customer_accounts
  status:   A=Active,       I=Inactive,       S=Suspended
  segment:  ENT=Enterprise, SMB=Small Business, CON=Consumer
  region:   DFW=Dallas, NYC=New York, LAX=Los Angeles,
            CHI=Chicago, HOU=Houston, ATL=Atlanta,
            SEA=Seattle, MIA=Miami, BOS=Boston

Table: service_subscriptions
  status:       A=Active, C=Cancelled, P=Paused
  service_type: FIBER=Fiber Internet, WIRELESS=Wireless,
                VOICE=Voice, DATA=Mobile Data, TV=Television

Table: network_kpis
  metric_name: UPTIME=Network Uptime Percentage,
               LATENCY_MS=Latency in Milliseconds,
               THROUGHPUT_MBPS=Throughput in Mbps,
               PACKET_LOSS_PCT=Packet Loss Percentage

Table: trouble_tickets
  priority: P1=Critical, P2=High, P3=Normal, P4=Low
  status:   O=Open, IP=In Progress, R=Resolved, C=Closed
  category: OUTAGE=Service Outage, BILLING=Billing Issue,
            SPEED=Speed/Performance, EQUIPMENT=Equipment Fault

Table: call_logs
  outcome_code: 1=Completed Call, 2=Busy,
                3=Dropped Call,   4=No Answer

Table: churn_events
  reason_code: PRICE=Price Too High, COVERAGE=Coverage Issues,
               SERVICE=Poor Service Quality,
               COMPETITOR=Switched to Competitor,
               MOVED=Customer Relocated

Table: orders
  status:     A=Active, C=Cancelled, P=Pending, F=Fulfilled
  order_type: NEW=New Activation, UPGRADE=Upgrade,
              DOWNGRADE=Downgrade, CANCEL=Cancellation
```

---

## 4. Audit Log Database

```sql
CREATE TABLE audit_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id          TEXT NOT NULL,      -- e.g. q_ab12cd34ef56
    user_id           TEXT NOT NULL,      -- JWT subject claim
    question          TEXT NOT NULL,      -- original user question
    selected_tables   TEXT NOT NULL,      -- comma-separated table names
    generated_sql     TEXT NOT NULL,      -- final executed SQL
    row_count         INTEGER DEFAULT 0,
    execution_time_ms INTEGER DEFAULT 0,
    status            TEXT NOT NULL,      -- SUCCESS|VALIDATION_ERROR|EXECUTION_ERROR
    error_message     TEXT NOT NULL DEFAULT '',
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);
```
