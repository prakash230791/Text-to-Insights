"""
Alert Service  (registry/alert_service.py)

Sends email notifications to the data team when the Delta Detector
finds unknown enumerated values that require manual curation.

Uses only Python stdlib smtplib — no external dependencies.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from config.settings import get_settings

if TYPE_CHECKING:
    from registry.delta_detector import DeltaReport

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self) -> None:
        cfg = get_settings()
        self._to = cfg.alert_email_to
        self._smtp_host = cfg.smtp_host
        self._smtp_port = cfg.smtp_port

    def send(self, report: "DeltaReport") -> None:
        """Send a summary email about schema changes. Logs on SMTP failure."""
        subject = f"[Text-to-Insights] Schema changes detected — {len(report.new_flagged_values)} unknown value(s)"
        body = self._build_body(report)

        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = "tti-bot@telecom.internal"
        msg["To"] = self._to

        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=10) as server:
                server.sendmail(msg["From"], [self._to], msg.as_string())
            logger.info("AlertService: email sent to %s", self._to)
        except Exception as exc:
            logger.error("AlertService: failed to send email — %s", exc)

    @staticmethod
    def _build_body(report: "DeltaReport") -> str:
        lines = [
            "Text-to-Insights — Automated Schema Change Alert",
            "=" * 50,
            "",
            report.summary(),
            "",
            "Action required:",
            "  1. Log into the Schema Registry admin UI",
            "  2. Navigate to the flagged values listed above",
            "  3. Add the correct human_label for each internal code",
            "  4. Mark each as is_manually_curated = True",
            "",
            "Until curated, these values will not appear in Value Mapper results.",
            "",
            "— Text-to-Insights Bot",
        ]
        return "\n".join(lines)
