"""Oracle Database client with connection pooling and read-only enforcement."""

from __future__ import annotations

import re
from typing import Any

import oracledb
import structlog

from src.config import OracleConfig

logger = structlog.get_logger(__name__)

# SQL statements that modify data — blocked in read-only mode
FORBIDDEN_PATTERNS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE|GRANT|REVOKE|"
    r"EXEC|EXECUTE|CALL|BEGIN|DECLARE|COMMIT|ROLLBACK|SAVEPOINT)\b",
    re.IGNORECASE,
)


class ReadOnlyViolationError(Exception):
    """Raised when a query attempts to modify data in read-only mode."""


class OracleClient:
    """Thread-safe Oracle database client with connection pooling."""

    def __init__(self, config: OracleConfig, read_only: bool = True) -> None:
        self._config = config
        self._read_only = read_only
        self._pool: oracledb.ConnectionPool | None = None

    async def initialize(self) -> None:
        """Create the connection pool."""
        try:
            dsn = oracledb.makedsn(
                self._config.host,
                self._config.port,
                service_name=self._config.service_name,
            )

            pool_params: dict[str, Any] = {
                "user": self._config.user,
                "password": self._config.password,
                "dsn": dsn,
                "min": self._config.min_connections,
                "max": self._config.max_connections,
                "timeout": self._config.connection_timeout,
            }

            if self._config.wallet_location:
                pool_params["wallet_location"] = self._config.wallet_location
                pool_params["wallet_password"] = self._config.wallet_password

            self._pool = oracledb.create_pool(**pool_params)
            logger.info("oracle_pool_created", min=self._config.min_connections, max=self._config.max_connections)
        except oracledb.Error as exc:
            logger.error("oracle_pool_creation_failed", error=str(exc))
            raise

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            self._pool.close(force=True)
            logger.info("oracle_pool_closed")

    def _validate_query(self, sql: str) -> None:
        """Enforce read-only mode by rejecting DDL/DML statements."""
        if self._read_only and FORBIDDEN_PATTERNS.search(sql):
            raise ReadOnlyViolationError(
                f"Query blocked: read-only mode is enabled. "
                f"Only SELECT statements are allowed. Received: {sql[:200]}"
            )

    async def execute_query(
        self, sql: str, params: dict[str, Any] | None = None, max_rows: int = 1000
    ) -> list[dict[str, Any]]:
        """Execute a read-only SQL query and return results as list of dicts."""
        self._validate_query(sql)

        if self._pool is None:
            raise RuntimeError("Oracle client not initialized. Call initialize() first.")

        connection = self._pool.acquire()
        try:
            cursor = connection.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)

                columns = [col[0] for col in cursor.description] if cursor.description else []
                rows = cursor.fetchmany(max_rows)

                return [dict(zip(columns, row, strict=False)) for row in rows]
            finally:
                cursor.close()
        except oracledb.Error as exc:
            logger.error("query_execution_failed", sql=sql[:200], error=str(exc))
            raise
        finally:
            self._pool.release(connection)

    async def get_all_tables(self) -> list[dict[str, Any]]:
        """Retrieve all accessible tables and views."""
        sql = """
            SELECT table_name, owner, tablespace_name, num_rows, last_analyzed
            FROM all_tables
            WHERE owner NOT IN ('SYS', 'SYSTEM', 'DBSNMP', 'APPQOSSYS', 'OUTLN', 'XDB')
            ORDER BY owner, table_name
        """
        return await self.execute_query(sql)

    async def describe_table(self, table_name: str, owner: str | None = None) -> dict[str, Any]:
        """Get detailed schema information for a specific table."""
        owner_filter = "AND owner = :owner" if owner else ""
        params: dict[str, Any] = {"table_name": table_name.upper()}
        if owner:
            params["owner"] = owner.upper()

        columns_sql = f"""
            SELECT column_name, data_type, data_length, data_precision, data_scale,
                   nullable, column_id, data_default
            FROM all_tab_columns
            WHERE table_name = :table_name {owner_filter}
            ORDER BY column_id
        """
        columns = await self.execute_query(columns_sql, params)

        constraints_sql = f"""
            SELECT constraint_name, constraint_type, search_condition, status
            FROM all_constraints
            WHERE table_name = :table_name {owner_filter}
            ORDER BY constraint_type
        """
        constraints = await self.execute_query(constraints_sql, params)

        indexes_sql = f"""
            SELECT index_name, index_type, uniqueness, status
            FROM all_indexes
            WHERE table_name = :table_name {owner_filter}
        """
        indexes = await self.execute_query(indexes_sql, params)

        row_count_sql = f"""
            SELECT num_rows, last_analyzed
            FROM all_tables
            WHERE table_name = :table_name {owner_filter}
        """
        stats = await self.execute_query(row_count_sql, params)

        sample_sql = f"SELECT * FROM {table_name} WHERE ROWNUM <= 5"
        try:
            sample_rows = await self.execute_query(sample_sql, max_rows=5)
        except oracledb.Error:
            sample_rows = []

        return {
            "table_name": table_name,
            "owner": owner or "CURRENT_SCHEMA",
            "columns": columns,
            "constraints": constraints,
            "indexes": indexes,
            "statistics": stats[0] if stats else {},
            "sample_rows": sample_rows,
        }

    async def get_table_comments(self, table_name: str, owner: str | None = None) -> dict[str, Any]:
        """Get table and column comments/descriptions."""
        owner_filter = "AND owner = :owner" if owner else ""
        params: dict[str, Any] = {"table_name": table_name.upper()}
        if owner:
            params["owner"] = owner.upper()

        table_comment_sql = f"""
            SELECT comments
            FROM all_tab_comments
            WHERE table_name = :table_name {owner_filter}
        """
        table_comments = await self.execute_query(table_comment_sql, params)

        column_comments_sql = f"""
            SELECT column_name, comments
            FROM all_col_comments
            WHERE table_name = :table_name {owner_filter}
            ORDER BY column_name
        """
        column_comments = await self.execute_query(column_comments_sql, params)

        return {
            "table_name": table_name,
            "table_comment": table_comments[0].get("COMMENTS", "") if table_comments else "",
            "column_comments": {row["COLUMN_NAME"]: row["COMMENTS"] for row in column_comments if row.get("COMMENTS")},
        }

    @property
    def is_connected(self) -> bool:
        """Check if the connection pool is active."""
        return self._pool is not None and self._pool.opened
