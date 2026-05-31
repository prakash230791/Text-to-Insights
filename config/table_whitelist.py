"""
Table whitelist — the only tables the SQL Validator will allow in generated queries.
Add any new table names here AND register them in the Schema Registry.
"""

ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        # Customer domain
        "customer_accounts",
        "customer_segments",
        # Service domain
        "service_subscriptions",
        "service_plans",
        # Network domain
        "network_kpis",
        "network_nodes",
        # Trouble tickets
        "trouble_tickets",
        "ticket_categories",
        # Revenue & billing
        "revenue_metrics",
        "billing_summary",
        # Call logs
        "call_logs",
        # Churn & retention
        "churn_events",
        # Referrals
        "referrals",
        # Orders
        "orders",
    }
)


def is_allowed(table_name: str) -> bool:
    return table_name.lower() in ALLOWED_TABLES
