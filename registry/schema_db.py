"""
Module 1 — Schema Registry  (registry/schema_db.py)

Four SQLAlchemy ORM models matching the design spec:
  • registry_tables   — one row per queryable table
  • registry_columns  — one row per column
  • registry_values   — one row per distinct enumerated value
  • registry_audit    — change log for all curated entries

SchemaDB class wraps all CRUD operations consumed by every other module.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, create_engine, func, select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

logger = logging.getLogger(__name__)


# ── ORM Models ─────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class RegistryTable(Base):
    """One row per table/view in the metrics server."""
    __tablename__ = "registry_tables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    domain: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    keywords: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    columns: Mapped[list["RegistryColumn"]] = relationship(
        "RegistryColumn", back_populates="table", cascade="all, delete-orphan"
    )
    values: Mapped[list["RegistryValue"]] = relationship(
        "RegistryValue", back_populates="table", cascade="all, delete-orphan"
    )


class RegistryColumn(Base):
    """One row per column of a tracked table."""
    __tablename__ = "registry_columns"
    __table_args__ = (
        UniqueConstraint("table_name", "column_name", name="uq_reg_col"),
        Index("ix_reg_col_table", "table_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(
        String(128), ForeignKey("registry_tables.table_name", ondelete="CASCADE"), nullable=False
    )
    column_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(64), nullable=False, default="TEXT")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_filterable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_metric: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dimension: Mapped[bool] = mapped_column(Boolean, default=False)
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True)
    sample_values: Mapped[str] = mapped_column(Text, nullable=False, default="")

    table: Mapped["RegistryTable"] = relationship("RegistryTable", back_populates="columns")


class RegistryValue(Base):
    """
    One row per distinct enumerated value for low-cardinality columns.
    e.g. (orders, status, 'A', 'Active')
    """
    __tablename__ = "registry_values"
    __table_args__ = (
        UniqueConstraint("table_name", "column_name", "internal_code", name="uq_reg_val"),
        Index("ix_reg_val_lookup", "table_name", "column_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(
        String(128), ForeignKey("registry_tables.table_name", ondelete="CASCADE"), nullable=False
    )
    column_name: Mapped[str] = mapped_column(String(128), nullable=False)
    internal_code: Mapped[str] = mapped_column(String(256), nullable=False)
    human_label: Mapped[str] = mapped_column(String(256), nullable=False)
    is_manually_curated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_flagged_unknown: Mapped[bool] = mapped_column(Boolean, default=False)

    table: Mapped["RegistryTable"] = relationship("RegistryTable", back_populates="values")


class RegistryAudit(Base):
    """Change log: when values were added, modified, or flagged unknown."""
    __tablename__ = "registry_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)   # ADDED|MODIFIED|FLAGGED
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # TABLE|COLUMN|VALUE
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    column_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    old_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    new_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── DTO classes ────────────────────────────────────────────────────────────────

@dataclass
class ColumnMeta:
    column_name: str
    data_type: str
    description: str
    sample_values: str
    is_filterable: bool
    is_metric: bool
    is_dimension: bool


@dataclass
class ValueMeta:
    internal_code: str
    human_label: str
    table_name: str
    column_name: str


@dataclass
class TableMeta:
    table_name: str
    description: str
    keywords: str
    domain: str
    columns: list[ColumnMeta] = field(default_factory=list)
    values: list[ValueMeta] = field(default_factory=list)


# ── SchemaDB ───────────────────────────────────────────────────────────────────

class SchemaDB:
    """
    Single interface for all registry read/write operations.

    Usage:
        db = SchemaDB("sqlite:///./data/registry.db")
        db.init_db()
        db.upsert_table("orders", "Order transactions", "order billing invoice", "billing")
    """

    def __init__(self, db_url: str) -> None:
        self._engine = create_engine(
            db_url, echo=False, connect_args={"check_same_thread": False}
        )
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)

    def init_db(self) -> None:
        Base.metadata.create_all(self._engine)
        logger.info("SchemaDB: tables created / verified")

    def session(self) -> Session:
        return self._Session()

    # ── Upsert helpers ─────────────────────────────────────────────────────────

    def upsert_table(
        self,
        table_name: str,
        description: str,
        keywords: str,
        domain: str = "general",
    ) -> None:
        with self._Session() as sess:
            obj = sess.scalar(
                select(RegistryTable).where(RegistryTable.table_name == table_name)
            )
            if obj is None:
                sess.add(RegistryTable(
                    table_name=table_name, description=description,
                    keywords=keywords, domain=domain,
                ))
                self._audit(sess, "ADDED", "TABLE", table_name, new_value=description)
            else:
                obj.description = description
                obj.keywords = keywords
                obj.domain = domain
            sess.commit()

    def upsert_column(
        self,
        table_name: str,
        column_name: str,
        data_type: str = "TEXT",
        description: str = "",
        sample_values: str = "",
        is_filterable: bool = True,
        is_metric: bool = False,
        is_dimension: bool = False,
        is_nullable: bool = True,
    ) -> None:
        with self._Session() as sess:
            obj = sess.scalar(
                select(RegistryColumn).where(
                    RegistryColumn.table_name == table_name,
                    RegistryColumn.column_name == column_name,
                )
            )
            if obj is None:
                sess.add(RegistryColumn(
                    table_name=table_name, column_name=column_name,
                    data_type=data_type, description=description,
                    sample_values=sample_values, is_filterable=is_filterable,
                    is_metric=is_metric, is_dimension=is_dimension,
                    is_nullable=is_nullable,
                ))
            else:
                obj.data_type = data_type
                obj.description = description
                obj.sample_values = sample_values
                obj.is_filterable = is_filterable
                obj.is_metric = is_metric
                obj.is_dimension = is_dimension
            sess.commit()

    def upsert_value(
        self,
        table_name: str,
        column_name: str,
        internal_code: str,
        human_label: str,
        is_manually_curated: bool = True,
    ) -> None:
        with self._Session() as sess:
            obj = sess.scalar(
                select(RegistryValue).where(
                    RegistryValue.table_name == table_name,
                    RegistryValue.column_name == column_name,
                    RegistryValue.internal_code == internal_code,
                )
            )
            if obj is None:
                sess.add(RegistryValue(
                    table_name=table_name, column_name=column_name,
                    internal_code=internal_code, human_label=human_label,
                    is_manually_curated=is_manually_curated,
                ))
                self._audit(
                    sess, "ADDED", "VALUE", table_name, column_name,
                    new_value=f"{internal_code}={human_label}",
                )
            else:
                old = obj.human_label
                obj.human_label = human_label
                obj.is_manually_curated = is_manually_curated
                obj.is_flagged_unknown = False
                if old != human_label:
                    self._audit(
                        sess, "MODIFIED", "VALUE", table_name, column_name,
                        old_value=f"{internal_code}={old}",
                        new_value=f"{internal_code}={human_label}",
                    )
            sess.commit()

    def flag_unknown_value(self, table_name: str, column_name: str, internal_code: str) -> None:
        """Mark a newly discovered value as unknown, pending manual curation."""
        with self._Session() as sess:
            obj = sess.scalar(
                select(RegistryValue).where(
                    RegistryValue.table_name == table_name,
                    RegistryValue.column_name == column_name,
                    RegistryValue.internal_code == internal_code,
                )
            )
            if obj is None:
                sess.add(RegistryValue(
                    table_name=table_name, column_name=column_name,
                    internal_code=internal_code, human_label=internal_code,
                    is_manually_curated=False, is_flagged_unknown=True,
                ))
                self._audit(
                    sess, "FLAGGED", "VALUE", table_name, column_name,
                    new_value=internal_code, notes="auto-detected, needs curation",
                )
                sess.commit()

    # ── Read operations ────────────────────────────────────────────────────────

    def list_tables(self, domain: Optional[str] = None) -> list[TableMeta]:
        with self._Session() as sess:
            q = select(RegistryTable).where(RegistryTable.is_active == True)
            if domain:
                q = q.where(RegistryTable.domain == domain)
            return [
                TableMeta(
                    table_name=r.table_name, description=r.description,
                    keywords=r.keywords, domain=r.domain,
                )
                for r in sess.scalars(q).all()
            ]

    def get_table_meta(self, table_name: str) -> Optional[TableMeta]:
        with self._Session() as sess:
            tbl = sess.scalar(
                select(RegistryTable).where(RegistryTable.table_name == table_name)
            )
            if tbl is None:
                return None
            cols = sess.scalars(
                select(RegistryColumn).where(RegistryColumn.table_name == table_name)
            ).all()
            vals = sess.scalars(
                select(RegistryValue).where(
                    RegistryValue.table_name == table_name,
                    RegistryValue.is_flagged_unknown == False,
                )
            ).all()
            return TableMeta(
                table_name=tbl.table_name, description=tbl.description,
                keywords=tbl.keywords, domain=tbl.domain,
                columns=[
                    ColumnMeta(
                        column_name=c.column_name, data_type=c.data_type,
                        description=c.description, sample_values=c.sample_values,
                        is_filterable=c.is_filterable, is_metric=c.is_metric,
                        is_dimension=c.is_dimension,
                    )
                    for c in cols
                ],
                values=[
                    ValueMeta(
                        internal_code=v.internal_code, human_label=v.human_label,
                        table_name=v.table_name, column_name=v.column_name,
                    )
                    for v in vals
                ],
            )

    def get_values_for_column(self, table_name: str, column_name: str) -> list[RegistryValue]:
        with self._Session() as sess:
            return list(sess.scalars(
                select(RegistryValue).where(
                    RegistryValue.table_name == table_name,
                    RegistryValue.column_name == column_name,
                )
            ).all())

    def get_all_values(self) -> list[RegistryValue]:
        with self._Session() as sess:
            return list(sess.scalars(select(RegistryValue)).all())

    def get_flagged_values(self) -> list[RegistryValue]:
        with self._Session() as sess:
            return list(sess.scalars(
                select(RegistryValue).where(RegistryValue.is_flagged_unknown == True)
            ).all())

    def build_ddl_block(self, table_names: list[str]) -> str:
        """Render CREATE TABLE DDL for prompt injection."""
        blocks: list[str] = []
        for name in table_names:
            meta = self.get_table_meta(name)
            if meta is None:
                continue
            col_lines = []
            for c in meta.columns:
                nullable = "" if False else ""  # all optional at DB level
                note = f"  -- {c.description}" if c.description else ""
                col_lines.append(f"    {c.column_name} {c.data_type}{note}")
            # Add enumerated values as a comment block
            val_lines = []
            for v in meta.values:
                val_lines.append(
                    f"--   {v.column_name}: '{v.internal_code}' = {v.human_label}"
                )
            val_block = ("\n-- Enumerated values:\n" + "\n".join(val_lines)) if val_lines else ""
            ddl = (
                f"-- {meta.description}\n"
                f"CREATE TABLE {name} (\n"
                + ",\n".join(col_lines)
                + f"\n);{val_block}"
            )
            blocks.append(ddl)
        return "\n\n".join(blocks)

    # ── Internal helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _audit(
        sess: Session,
        event_type: str,
        entity_type: str,
        table_name: str,
        column_name: str = "",
        old_value: str = "",
        new_value: str = "",
        notes: str = "",
    ) -> None:
        sess.add(RegistryAudit(
            event_type=event_type, entity_type=entity_type,
            table_name=table_name, column_name=column_name,
            old_value=old_value, new_value=new_value, notes=notes,
        ))
