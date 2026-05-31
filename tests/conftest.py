"""
Shared pytest fixtures for all test modules.

Uses in-memory SQLite for both the registry and metrics DBs so tests
run without any external processes or files.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from registry.schema_db import SchemaDB


@pytest.fixture(scope="session")
def registry_db() -> SchemaDB:
    """Schema Registry backed by an in-memory SQLite database."""
    db = SchemaDB("sqlite:///:memory:")
    db.init_db()

    # ── customer_accounts ─────────────────────────────────────────────────────
    db.upsert_table(
        "customer_accounts",
        description="Customer master records including status, segment, and market region",
        keywords="customer account subscriber segment region market active inactive",
        domain="customer",
    )
    db.upsert_column("customer_accounts", "customer_id",  "INTEGER", "Unique customer ID",     is_dimension=True)
    db.upsert_column("customer_accounts", "status",       "TEXT",    "Account status code",     is_dimension=True)
    db.upsert_column("customer_accounts", "segment",      "TEXT",    "Customer segment",        is_dimension=True)
    db.upsert_column("customer_accounts", "region",       "TEXT",    "Market region code",      is_dimension=True)
    db.upsert_column("customer_accounts", "mrr",          "REAL",    "Monthly recurring revenue", is_metric=True)

    db.upsert_value("customer_accounts", "status", "A", "Active")
    db.upsert_value("customer_accounts", "status", "I", "Inactive")
    db.upsert_value("customer_accounts", "status", "S", "Suspended")
    db.upsert_value("customer_accounts", "region", "DFW", "Dallas")
    db.upsert_value("customer_accounts", "region", "NYC", "New York")
    db.upsert_value("customer_accounts", "segment", "ENT", "Enterprise")
    db.upsert_value("customer_accounts", "segment", "SMB", "Small Business")

    # ── trouble_tickets ───────────────────────────────────────────────────────
    db.upsert_table(
        "trouble_tickets",
        description="Customer trouble tickets and service complaints",
        keywords="ticket complaint issue problem priority status resolved open",
        domain="customer",
    )
    db.upsert_column("trouble_tickets", "ticket_id",  "INTEGER", "Unique ticket ID",    is_dimension=True)
    db.upsert_column("trouble_tickets", "priority",   "TEXT",    "Priority level",      is_dimension=True)
    db.upsert_column("trouble_tickets", "status",     "TEXT",    "Ticket status",       is_dimension=True)
    db.upsert_column("trouble_tickets", "category",   "TEXT",    "Ticket category",     is_dimension=True)
    db.upsert_column("trouble_tickets", "region",     "TEXT",    "Region code",         is_dimension=True)

    db.upsert_value("trouble_tickets", "priority", "P1", "Critical")
    db.upsert_value("trouble_tickets", "priority", "P2", "High")
    db.upsert_value("trouble_tickets", "priority", "P3", "Normal")
    db.upsert_value("trouble_tickets", "status",   "O",  "Open")
    db.upsert_value("trouble_tickets", "status",   "R",  "Resolved")

    # ── call_logs ─────────────────────────────────────────────────────────────
    db.upsert_table(
        "call_logs",
        description="Individual call detail records for voice and data calls",
        keywords="call cdr voice dropped completed duration outcome region",
        domain="network",
    )
    db.upsert_column("call_logs", "call_id",      "INTEGER", "Unique call ID",          is_dimension=True)
    db.upsert_column("call_logs", "outcome_code", "TEXT",    "Call outcome code",       is_dimension=True)
    db.upsert_column("call_logs", "region",       "TEXT",    "Call region",             is_dimension=True)
    db.upsert_column("call_logs", "duration_sec", "INTEGER", "Duration in seconds",     is_metric=True)

    db.upsert_value("call_logs", "outcome_code", "1", "Completed Call")
    db.upsert_value("call_logs", "outcome_code", "3", "Dropped Call")

    return db


@pytest.fixture(scope="session")
def metrics_engine():
    """In-memory SQLite metrics DB for executor tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE customer_accounts (
                customer_id INTEGER PRIMARY KEY,
                status TEXT, segment TEXT, region TEXT, mrr REAL
            )
        """))
        conn.execute(text("""
            INSERT INTO customer_accounts VALUES
                (1,'A','ENT','DFW',1200.0),
                (2,'A','SMB','DFW',300.0),
                (3,'I','CON','NYC',50.0),
                (4,'A','ENT','NYC',2000.0),
                (5,'S','SMB','DFW',0.0)
        """))
    return engine
