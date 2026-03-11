"""Tests for the Oracle client — focuses on read-only enforcement and query validation."""

from __future__ import annotations

import pytest

from src.config import OracleConfig
from src.oracle_client import OracleClient, ReadOnlyViolationError


@pytest.fixture
def readonly_client() -> OracleClient:
    config = OracleConfig(host="localhost", port=1521, service_name="ORCL", user="test", password="test")
    return OracleClient(config, read_only=True)


@pytest.fixture
def readwrite_client() -> OracleClient:
    config = OracleConfig(host="localhost", port=1521, service_name="ORCL", user="test", password="test")
    return OracleClient(config, read_only=False)


class TestReadOnlyEnforcement:
    """Verify that the read-only guard blocks dangerous SQL."""

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO users (name) VALUES ('test')",
            "UPDATE users SET name = 'test' WHERE id = 1",
            "DELETE FROM users WHERE id = 1",
            "DROP TABLE users",
            "CREATE TABLE test (id INT)",
            "ALTER TABLE users ADD COLUMN age INT",
            "TRUNCATE TABLE users",
            "MERGE INTO target USING source ON (target.id = source.id) WHEN MATCHED THEN UPDATE SET name = source.name",
            "GRANT SELECT ON users TO public",
            "REVOKE SELECT ON users FROM public",
            "EXEC dbms_output.put_line('hello')",
            "BEGIN NULL; END;",
            "COMMIT",
            "ROLLBACK",
        ],
    )
    def test_blocks_dangerous_sql(self, readonly_client: OracleClient, sql: str) -> None:
        with pytest.raises(ReadOnlyViolationError):
            readonly_client._validate_query(sql)

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM users",
            "SELECT COUNT(*) FROM sales WHERE region = 'East'",
            "SELECT a.name, b.amount FROM users a JOIN orders b ON a.id = b.user_id",
            "SELECT * FROM all_tables WHERE owner = 'SALES'",
            "WITH cte AS (SELECT * FROM users) SELECT * FROM cte",
        ],
    )
    def test_allows_select_queries(self, readonly_client: OracleClient, sql: str) -> None:
        # Should not raise
        readonly_client._validate_query(sql)

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO users (name) VALUES ('test')",
            "DROP TABLE users",
        ],
    )
    def test_readwrite_allows_all(self, readwrite_client: OracleClient, sql: str) -> None:
        # Should not raise when read_only=False
        readwrite_client._validate_query(sql)


class TestClientLifecycle:
    """Test client initialization state."""

    def test_not_connected_before_init(self, readonly_client: OracleClient) -> None:
        assert not readonly_client.is_connected

    @pytest.mark.asyncio
    async def test_execute_before_init_raises(self, readonly_client: OracleClient) -> None:
        with pytest.raises(RuntimeError, match="not initialized"):
            await readonly_client.execute_query("SELECT 1 FROM DUAL")
