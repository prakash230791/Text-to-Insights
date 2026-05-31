"""
Telecom Schema Seed Script  (scripts/seed_telecom.py)

Populates the Schema Registry with a realistic telecom OSS/BSS schema
AND creates a sample metrics SQLite DB with synthetic data for testing.

Run once after initial setup:
    python -m scripts.seed_telecom

Tables seeded:
  • customer_accounts   — customer master data
  • service_subscriptions — services per customer
  • network_kpis        — daily network performance KPIs
  • trouble_tickets     — customer trouble tickets
  • revenue_metrics     — aggregated revenue by market/product
  • call_logs           — individual call detail records
  • churn_events        — churn tracking
  • orders              — service orders
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure project root is on path when run as a module
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

from config.settings import get_settings
from registry.schema_db import SchemaDB

cfg = get_settings()


# ── Registry seeding ───────────────────────────────────────────────────────────

def seed_registry(db: SchemaDB) -> None:
    print("Seeding Schema Registry …")

    # ── customer_accounts ─────────────────────────────────────────────────────
    db.upsert_table(
        "customer_accounts",
        description="Customer master records including status, segment, and market region",
        keywords="customer account subscriber segment region market active inactive churn",
        domain="customer",
    )
    for col, dtype, desc, is_dim, is_met in [
        ("customer_id",    "INTEGER", "Unique customer identifier",                      True,  False),
        ("name",           "TEXT",    "Customer full name or company name",              True,  False),
        ("status",         "TEXT",    "Account status code: A=Active, I=Inactive, S=Suspended", True, False),
        ("segment",        "TEXT",    "Customer segment: ENT=Enterprise, SMB=Small Business, CON=Consumer", True, False),
        ("region",         "TEXT",    "Market region code e.g. DFW, NYC, LAX",          True,  False),
        ("mrr",            "REAL",    "Monthly recurring revenue in USD",               False, True),
        ("created_date",   "DATE",    "Account creation date",                          True,  False),
        ("account_manager","TEXT",    "Assigned account manager name",                  True,  False),
    ]:
        db.upsert_column("customer_accounts", col, dtype, desc,
                         is_dimension=is_dim, is_metric=is_met)

    for code, label in [
        ("A", "Active"), ("I", "Inactive"), ("S", "Suspended"),
    ]:
        db.upsert_value("customer_accounts", "status", code, label)

    for code, label in [
        ("ENT", "Enterprise"), ("SMB", "Small Business"), ("CON", "Consumer"),
    ]:
        db.upsert_value("customer_accounts", "segment", code, label)

    for code, label in [
        ("DFW", "Dallas"), ("NYC", "New York"), ("LAX", "Los Angeles"),
        ("CHI", "Chicago"), ("HOU", "Houston"), ("ATL", "Atlanta"),
        ("SEA", "Seattle"), ("MIA", "Miami"), ("BOS", "Boston"),
    ]:
        db.upsert_value("customer_accounts", "region", code, label)

    # ── service_subscriptions ─────────────────────────────────────────────────
    db.upsert_table(
        "service_subscriptions",
        description="Active and historical service subscriptions per customer",
        keywords="service subscription plan product fiber broadband voice wireless data",
        domain="customer",
    )
    for col, dtype, desc, is_dim, is_met in [
        ("subscription_id", "INTEGER", "Unique subscription identifier",               True,  False),
        ("customer_id",     "INTEGER", "FK to customer_accounts",                      True,  False),
        ("service_type",    "TEXT",    "Type of service: FIBER, WIRELESS, VOICE, DATA", True, False),
        ("plan_name",       "TEXT",    "Commercial plan name",                          True,  False),
        ("status",          "TEXT",    "Subscription status: A=Active, C=Cancelled, P=Paused", True, False),
        ("monthly_charge",  "REAL",    "Monthly charge in USD",                        False, True),
        ("start_date",      "DATE",    "Subscription start date",                      True,  False),
        ("end_date",        "DATE",    "Subscription end date (null if active)",        True,  False),
    ]:
        db.upsert_column("service_subscriptions", col, dtype, desc,
                         is_dimension=is_dim, is_metric=is_met)

    for code, label in [
        ("A", "Active"), ("C", "Cancelled"), ("P", "Paused"),
    ]:
        db.upsert_value("service_subscriptions", "status", code, label)

    for code, label in [
        ("FIBER", "Fiber Internet"), ("WIRELESS", "Wireless"), ("VOICE", "Voice"),
        ("DATA", "Mobile Data"), ("TV", "Television"),
    ]:
        db.upsert_value("service_subscriptions", "service_type", code, label)

    # ── network_kpis ──────────────────────────────────────────────────────────
    db.upsert_table(
        "network_kpis",
        description="Daily network performance KPIs by region and node",
        keywords="network kpi performance uptime latency throughput packet loss node region availability",
        domain="network",
    )
    for col, dtype, desc, is_dim, is_met in [
        ("kpi_date",     "DATE",    "Measurement date",                            True,  False),
        ("region",       "TEXT",    "Market region code",                          True,  False),
        ("node_id",      "TEXT",    "Network node identifier",                     True,  False),
        ("metric_name",  "TEXT",    "KPI name: UPTIME, LATENCY_MS, THROUGHPUT_MBPS, PACKET_LOSS_PCT", True, False),
        ("metric_value", "REAL",    "Measured value for the KPI",                 False, True),
        ("threshold",    "REAL",    "Target threshold for the KPI",               False, True),
        ("is_breached",  "INTEGER", "1 if metric_value violated threshold, else 0", True, False),
    ]:
        db.upsert_column("network_kpis", col, dtype, desc,
                         is_dimension=is_dim, is_metric=is_met)

    for code, label in [
        ("UPTIME",           "Network Uptime Percentage"),
        ("LATENCY_MS",       "Latency in Milliseconds"),
        ("THROUGHPUT_MBPS",  "Throughput in Mbps"),
        ("PACKET_LOSS_PCT",  "Packet Loss Percentage"),
    ]:
        db.upsert_value("network_kpis", "metric_name", code, label)

    # ── trouble_tickets ───────────────────────────────────────────────────────
    db.upsert_table(
        "trouble_tickets",
        description="Customer trouble tickets and service complaints",
        keywords="ticket complaint issue problem outage priority status resolved open customer support",
        domain="customer",
    )
    for col, dtype, desc, is_dim, is_met in [
        ("ticket_id",    "INTEGER", "Unique ticket identifier",                    True,  False),
        ("customer_id",  "INTEGER", "FK to customer_accounts",                     True,  False),
        ("category",     "TEXT",    "Ticket category: OUTAGE, BILLING, SPEED, EQUIPMENT, OTHER", True, False),
        ("priority",     "TEXT",    "Priority level: P1=Critical, P2=High, P3=Normal, P4=Low", True, False),
        ("status",       "TEXT",    "Ticket status: O=Open, IP=In Progress, R=Resolved, C=Closed", True, False),
        ("region",       "TEXT",    "Region where the issue occurred",             True,  False),
        ("created_at",   "DATETIME","Ticket creation timestamp",                   True,  False),
        ("resolved_at",  "DATETIME","Resolution timestamp (null if open)",         True,  False),
        ("resolution_hours","REAL", "Hours from creation to resolution",          False, True),
    ]:
        db.upsert_column("trouble_tickets", col, dtype, desc,
                         is_dimension=is_dim, is_metric=is_met)

    for code, label in [
        ("P1", "Critical"), ("P2", "High"), ("P3", "Normal"), ("P4", "Low"),
    ]:
        db.upsert_value("trouble_tickets", "priority", code, label)

    for code, label in [
        ("O", "Open"), ("IP", "In Progress"), ("R", "Resolved"), ("C", "Closed"),
    ]:
        db.upsert_value("trouble_tickets", "status", code, label)

    for code, label in [
        ("OUTAGE", "Service Outage"), ("BILLING", "Billing Issue"),
        ("SPEED", "Speed/Performance"), ("EQUIPMENT", "Equipment Fault"),
        ("OTHER", "Other"),
    ]:
        db.upsert_value("trouble_tickets", "category", code, label)

    # ── revenue_metrics ───────────────────────────────────────────────────────
    db.upsert_table(
        "revenue_metrics",
        description="Aggregated monthly revenue by market region and product line",
        keywords="revenue arpu mrr monthly recurring billing income product market region",
        domain="billing",
    )
    for col, dtype, desc, is_dim, is_met in [
        ("metric_month",  "DATE",   "First day of the reporting month",            True,  False),
        ("region",        "TEXT",   "Market region code",                          True,  False),
        ("product_line",  "TEXT",   "Product line: FIBER, WIRELESS, VOICE, DATA",  True,  False),
        ("total_revenue", "REAL",   "Total revenue in USD for the period",         False, True),
        ("arpu",          "REAL",   "Average revenue per user in USD",             False, True),
        ("subscriber_count","INTEGER","Number of active subscribers at month end", False, True),
        ("churn_rate_pct","REAL",   "Churn rate percentage for the period",        False, True),
    ]:
        db.upsert_column("revenue_metrics", col, dtype, desc,
                         is_dimension=is_dim, is_metric=is_met)

    # ── call_logs ─────────────────────────────────────────────────────────────
    db.upsert_table(
        "call_logs",
        description="Individual call detail records (CDRs) for voice and data calls",
        keywords="call cdr voice dropped completed duration outcome region node",
        domain="network",
    )
    for col, dtype, desc, is_dim, is_met in [
        ("call_id",      "INTEGER", "Unique call identifier",                      True,  False),
        ("customer_id",  "INTEGER", "FK to customer_accounts",                     True,  False),
        ("call_date",    "DATE",    "Date of the call",                            True,  False),
        ("region",       "TEXT",    "Region where the call originated",            True,  False),
        ("node_id",      "TEXT",    "Network node that handled the call",          True,  False),
        ("outcome_code", "TEXT",    "Call outcome: 1=Completed, 2=Busy, 3=Dropped, 4=No Answer", True, False),
        ("duration_sec", "INTEGER", "Call duration in seconds",                    False, True),
    ]:
        db.upsert_column("call_logs", col, dtype, desc,
                         is_dimension=is_dim, is_metric=is_met)

    for code, label in [
        ("1", "Completed Call"), ("2", "Busy"), ("3", "Dropped Call"), ("4", "No Answer"),
    ]:
        db.upsert_value("call_logs", "outcome_code", code, label)

    # ── churn_events ──────────────────────────────────────────────────────────
    db.upsert_table(
        "churn_events",
        description="Customer churn events with reason codes and lifetime value",
        keywords="churn cancel leave reason ltv lifetime value retention",
        domain="customer",
    )
    for col, dtype, desc, is_dim, is_met in [
        ("event_id",     "INTEGER", "Unique event identifier",                     True,  False),
        ("customer_id",  "INTEGER", "FK to customer_accounts",                     True,  False),
        ("churn_date",   "DATE",    "Date customer churned",                       True,  False),
        ("reason_code",  "TEXT",    "Churn reason: PRICE, COVERAGE, SERVICE, COMPETITOR, MOVED", True, False),
        ("region",       "TEXT",    "Region of churned customer",                  True,  False),
        ("lifetime_value","REAL",   "Customer lifetime value in USD at churn",     False, True),
        ("tenure_months","INTEGER", "Customer tenure in months at churn",          False, True),
    ]:
        db.upsert_column("churn_events", col, dtype, desc,
                         is_dimension=is_dim, is_metric=is_met)

    for code, label in [
        ("PRICE", "Price Too High"), ("COVERAGE", "Coverage Issues"),
        ("SERVICE", "Poor Service Quality"), ("COMPETITOR", "Switched to Competitor"),
        ("MOVED", "Customer Relocated"),
    ]:
        db.upsert_value("churn_events", "reason_code", code, label)

    # ── orders ────────────────────────────────────────────────────────────────
    db.upsert_table(
        "orders",
        description="Service orders placed by customers (new, upgrades, cancellations)",
        keywords="order purchase new upgrade downgrade cancel billing invoice",
        domain="billing",
    )
    for col, dtype, desc, is_dim, is_met in [
        ("order_id",     "INTEGER", "Unique order identifier",                     True,  False),
        ("customer_id",  "INTEGER", "FK to customer_accounts",                     True,  False),
        ("order_date",   "DATE",    "Date order was placed",                       True,  False),
        ("order_type",   "TEXT",    "Order type: NEW, UPGRADE, DOWNGRADE, CANCEL", True,  False),
        ("status",       "TEXT",    "Order status: A=Active, C=Cancelled, P=Pending, F=Fulfilled", True, False),
        ("region",       "TEXT",    "Customer region for the order",               True,  False),
        ("product_line", "TEXT",    "Product ordered: FIBER, WIRELESS, VOICE",     True,  False),
        ("order_value",  "REAL",    "Order value in USD",                          False, True),
    ]:
        db.upsert_column("orders", col, dtype, desc,
                         is_dimension=is_dim, is_metric=is_met)

    for code, label in [
        ("A", "Active"), ("C", "Cancelled"), ("P", "Pending"), ("F", "Fulfilled"),
    ]:
        db.upsert_value("orders", "status", code, label)

    for code, label in [
        ("NEW", "New Activation"), ("UPGRADE", "Upgrade"),
        ("DOWNGRADE", "Downgrade"), ("CANCEL", "Cancellation"),
    ]:
        db.upsert_value("orders", "order_type", code, label)

    print("  ✓ Registry seeded: 8 tables, columns, and value mappings")


# ── Sample metrics DB ──────────────────────────────────────────────────────────

REGIONS = ["DFW", "NYC", "LAX", "CHI", "HOU", "ATL"]
SEGMENTS = ["ENT", "SMB", "CON"]
STATUSES_CUST = ["A", "A", "A", "I", "S"]   # weighted toward Active
SERVICE_TYPES = ["FIBER", "WIRELESS", "VOICE", "DATA", "TV"]
PRIORITIES = ["P1", "P2", "P3", "P3", "P4"]
TICKET_CATS = ["OUTAGE", "BILLING", "SPEED", "EQUIPMENT", "OTHER"]
TICKET_STATUSES = ["O", "IP", "R", "C"]
CALL_OUTCOMES = ["1", "1", "1", "2", "3", "4"]
CHURN_REASONS = ["PRICE", "COVERAGE", "SERVICE", "COMPETITOR", "MOVED"]
ORDER_TYPES = ["NEW", "UPGRADE", "DOWNGRADE", "CANCEL"]
PRODUCT_LINES = ["FIBER", "WIRELESS", "VOICE"]


def _rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def seed_metrics_db(metrics_url: str, n_customers: int = 500) -> None:
    print(f"Creating sample metrics DB at {metrics_url} …")
    engine = create_engine(metrics_url, echo=False)

    with engine.begin() as conn:
        # Create tables
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS customer_accounts (
                customer_id INTEGER PRIMARY KEY,
                name TEXT, status TEXT, segment TEXT, region TEXT,
                mrr REAL, created_date DATE, account_manager TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS service_subscriptions (
                subscription_id INTEGER PRIMARY KEY,
                customer_id INTEGER, service_type TEXT, plan_name TEXT, status TEXT,
                monthly_charge REAL, start_date DATE, end_date DATE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS network_kpis (
                kpi_date DATE, region TEXT, node_id TEXT, metric_name TEXT,
                metric_value REAL, threshold REAL, is_breached INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS trouble_tickets (
                ticket_id INTEGER PRIMARY KEY,
                customer_id INTEGER, category TEXT, priority TEXT, status TEXT,
                region TEXT, created_at DATETIME, resolved_at DATETIME, resolution_hours REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS revenue_metrics (
                metric_month DATE, region TEXT, product_line TEXT,
                total_revenue REAL, arpu REAL, subscriber_count INTEGER, churn_rate_pct REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS call_logs (
                call_id INTEGER PRIMARY KEY,
                customer_id INTEGER, call_date DATE, region TEXT, node_id TEXT,
                outcome_code TEXT, duration_sec INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS churn_events (
                event_id INTEGER PRIMARY KEY,
                customer_id INTEGER, churn_date DATE, reason_code TEXT,
                region TEXT, lifetime_value REAL, tenure_months INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER, order_date DATE, order_type TEXT, status TEXT,
                region TEXT, product_line TEXT, order_value REAL
            )
        """))

        today = date.today()
        start_date = today - timedelta(days=365)

        # customer_accounts
        customers = []
        for i in range(1, n_customers + 1):
            r = random.choice(REGIONS)
            s = random.choice(STATUSES_CUST)
            seg = random.choice(SEGMENTS)
            mrr = round(random.uniform(50, 5000) if seg == "ENT" else random.uniform(20, 500), 2)
            cd = _rand_date(start_date, today)
            conn.execute(text(
                "INSERT INTO customer_accounts VALUES (:cid,:nm,:st,:seg,:reg,:mrr,:cd,:am)"
            ), {"cid": i, "nm": f"Customer {i}", "st": s, "seg": seg,
                "reg": r, "mrr": mrr, "cd": cd.isoformat(), "am": f"AM_{r}"})
            customers.append({"id": i, "region": r, "status": s})

        # service_subscriptions
        sub_id = 1
        for c in customers:
            for _ in range(random.randint(1, 3)):
                svc = random.choice(SERVICE_TYPES)
                st = random.choice(["A", "A", "C", "P"])
                sd = _rand_date(start_date, today)
                ed = None if st == "A" else _rand_date(sd, today)
                conn.execute(text(
                    "INSERT INTO service_subscriptions VALUES (:sid,:cid,:svc,:plan,:st,:mc,:sd,:ed)"
                ), {"sid": sub_id, "cid": c["id"], "svc": svc, "plan": f"{svc}_PLAN",
                    "st": st, "mc": round(random.uniform(20, 300), 2),
                    "sd": sd.isoformat(), "ed": ed.isoformat() if ed else None})
                sub_id += 1

        # network_kpis (last 90 days, 6 regions x 3 nodes x 4 metrics)
        kpi_thresholds = {"UPTIME": 99.5, "LATENCY_MS": 50, "THROUGHPUT_MBPS": 100, "PACKET_LOSS_PCT": 1.0}
        for days_back in range(90):
            d = (today - timedelta(days=days_back)).isoformat()
            for region in REGIONS:
                for node in ["N1", "N2", "N3"]:
                    for metric, thresh in kpi_thresholds.items():
                        if metric == "UPTIME":
                            val = round(random.uniform(98.0, 100.0), 3)
                        elif metric == "LATENCY_MS":
                            val = round(random.uniform(10, 80), 1)
                        elif metric == "THROUGHPUT_MBPS":
                            val = round(random.uniform(50, 200), 1)
                        else:
                            val = round(random.uniform(0, 3), 3)
                        breached = 1 if (
                            (metric in ("UPTIME", "THROUGHPUT_MBPS") and val < thresh) or
                            (metric in ("LATENCY_MS", "PACKET_LOSS_PCT") and val > thresh)
                        ) else 0
                        conn.execute(text(
                            "INSERT INTO network_kpis VALUES (:d,:r,:n,:m,:v,:t,:b)"
                        ), {"d": d, "r": region, "n": node, "m": metric,
                            "v": val, "t": thresh, "b": breached})

        # trouble_tickets
        for tid in range(1, 1001):
            c = random.choice(customers)
            cat = random.choice(TICKET_CATS)
            pri = random.choice(PRIORITIES)
            st = random.choice(TICKET_STATUSES)
            cd = _rand_date(start_date, today)
            rd = _rand_date(cd, today) if st in ("R", "C") else None
            rh = round((rd - cd).total_seconds() / 3600, 1) if rd else None
            conn.execute(text(
                "INSERT INTO trouble_tickets VALUES (:tid,:cid,:cat,:pri,:st,:reg,:cd,:rd,:rh)"
            ), {"tid": tid, "cid": c["id"], "cat": cat, "pri": pri, "st": st,
                "reg": c["region"], "cd": cd.isoformat(), "rd": rd.isoformat() if rd else None,
                "rh": rh})

        # revenue_metrics (last 12 months)
        for months_back in range(12):
            first_of_month = (today.replace(day=1) - timedelta(days=months_back * 30)).replace(day=1)
            for region in REGIONS:
                for product in PRODUCT_LINES:
                    subs = random.randint(500, 5000)
                    arpu = round(random.uniform(30, 120), 2)
                    conn.execute(text(
                        "INSERT INTO revenue_metrics VALUES (:m,:r,:p,:tr,:arpu,:sc,:churn)"
                    ), {"m": first_of_month.isoformat(), "r": region, "p": product,
                        "tr": round(subs * arpu, 2), "arpu": arpu, "sc": subs,
                        "churn": round(random.uniform(0.5, 5.0), 2)})

        # call_logs
        for cid in range(1, 5001):
            c = random.choice(customers)
            cd = _rand_date(start_date, today)
            conn.execute(text(
                "INSERT INTO call_logs VALUES (:cid,:cusid,:cd,:reg,:node,:oc,:dur)"
            ), {"cid": cid, "cusid": c["id"], "cd": cd.isoformat(),
                "reg": c["region"], "node": f"N{random.randint(1,3)}",
                "oc": random.choice(CALL_OUTCOMES), "dur": random.randint(0, 3600)})

        # churn_events (10% of customers)
        eid = 1
        for c in random.sample(customers, k=n_customers // 10):
            cd = _rand_date(start_date, today)
            conn.execute(text(
                "INSERT INTO churn_events VALUES (:eid,:cid,:cd,:rc,:reg,:ltv,:ten)"
            ), {"eid": eid, "cid": c["id"], "cd": cd.isoformat(),
                "rc": random.choice(CHURN_REASONS), "reg": c["region"],
                "ltv": round(random.uniform(500, 50000), 2),
                "ten": random.randint(1, 60)})
            eid += 1

        # orders
        for oid in range(1, 2001):
            c = random.choice(customers)
            od = _rand_date(start_date, today)
            conn.execute(text(
                "INSERT INTO orders VALUES (:oid,:cid,:od,:otype,:st,:reg,:pl,:ov)"
            ), {"oid": oid, "cid": c["id"], "od": od.isoformat(),
                "otype": random.choice(ORDER_TYPES), "st": random.choice(["A", "F", "C", "P"]),
                "reg": c["region"], "pl": random.choice(PRODUCT_LINES),
                "ov": round(random.uniform(50, 2000), 2)})

    print(f"  ✓ Metrics DB created with {n_customers} customers and sample data")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import random as _r
    _r.seed(42)

    # Ensure data/ directory exists
    Path("data").mkdir(exist_ok=True)

    db = SchemaDB(cfg.registry_db_url)
    db.init_db()
    seed_registry(db)

    seed_metrics_db(cfg.metrics_db_url)

    print("\nSetup complete!")
    print(f"  Registry DB : {cfg.registry_db_url}")
    print(f"  Metrics DB  : {cfg.metrics_db_url}")
    print("\nNext steps:")
    print("  1.  ollama pull sqlcoder && ollama pull mistral")
    print("  2.  uvicorn api.main:app --reload")
    print("  3.  streamlit run ui/app.py")
