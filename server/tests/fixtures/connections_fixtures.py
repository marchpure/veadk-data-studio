import base64
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.connections import Connection


class ConnectionTestHelper:
    async def create_connection(
        self, client: AsyncClient, conn_type: str, connection_obj: dict[str, Any], expect_success: bool = True
    ) -> dict[str, Any] | None:
        payload = {"type": conn_type, "connection_obj": connection_obj}

        response = await client.post("/api/connections", json=payload)

        if expect_success:
            assert response.status_code == 201
            return response.json()
        else:
            assert response.status_code >= 400
            return None

    async def update_connection(
        self,
        client: AsyncClient,
        connection_id: str,
        conn_type: str,
        connection_obj: dict[str, Any],
        expect_success: bool = True,
    ) -> dict[str, Any] | None:
        """
        Update an existing connection via API.

        Args:
            client: Test HTTP client
            connection_id: ID of connection to update
            conn_type: New connection type
            connection_obj: New connection configuration
            expect_success: Whether to expect successful update

        Returns:
            Updated connection data if successful, None otherwise
        """
        payload = {"type": conn_type, "connection_obj": connection_obj}

        response = await client.put(f"/api/connections/{connection_id}", json=payload)

        if expect_success:
            assert response.status_code == 200
            return response.json()
        else:
            assert response.status_code >= 400
            return None

    async def list_connections(self, client: AsyncClient) -> dict[str, Any]:
        """
        List all connections via API.

        Args:
            client: Test HTTP client

        Returns:
            List response containing items and total count
        """
        response = await client.get("/api/connections")
        assert response.status_code == 200
        return response.json()

    async def verify_connection_encryption(
        self, session: AsyncSession, connection_id: str, sensitive_values: list[str]
    ) -> bool:
        """
        Verify that sensitive values are encrypted in the database.

        Args:
            session: Database session
            connection_id: Connection ID to check
            sensitive_values: List of sensitive strings that should not appear in encrypted data

        Returns:
            True if properly encrypted, False otherwise
        """
        result = await session.execute(select(Connection).where(Connection.id == connection_id))
        connection = result.scalar_one_or_none()

        if not connection:
            return False

        encrypted_data = connection.connection_obj_encrypted

        # Check that sensitive values don't appear in encrypted data
        for value in sensitive_values:
            if value in encrypted_data:
                return False

        # Verify it's base64 encoded
        try:
            base64.b64decode(encrypted_data)
            return True
        except Exception:
            return False

    async def get_decrypted_connection(self, session: AsyncSession, connection_id: str) -> dict[str, Any] | None:
        """
        Get decrypted connection data directly from database.

        Args:
            session: Database session
            connection_id: Connection ID to retrieve

        Returns:
            Decrypted connection object or None if not found
        """
        result = await session.execute(select(Connection).where(Connection.id == connection_id))
        connection = result.scalar_one_or_none()

        if connection:
            return await connection.get_decrypted_connection_obj(session)
        return None


class ConnectionDataFactory:
    """Factory for generating various connection configurations."""

    @staticmethod
    def create_pg_config(
        host: str = "localhost",
        port: int = 5432,
        database: str = "testdb",
        username: str = "testuser",
        password: str = "testpass",
        **kwargs,
    ) -> dict[str, Any]:
        """Create PostgreSQL connection configuration."""
        config = {"host": host, "port": port, "database": database, "username": username, "password": password}
        config.update(kwargs)
        return config

    @staticmethod
    def create_mysql_config(
        host: str = "localhost",
        port: int = 3306,
        database: str = "testdb",
        username: str = "mysqluser",
        password: str = "mysqlpass",
        **kwargs,
    ) -> dict[str, Any]:
        """Create MySQL connection configuration."""
        config = {"host": host, "port": port, "database": database, "username": username, "password": password}
        config.update(kwargs)
        return config

    @staticmethod
    def create_mongo_config(
        connection_string: str | None = None,
        host: str = "localhost",
        port: int = 27017,
        database: str = "testdb",
        username: str = "mongouser",
        password: str = "mongopass",
        **kwargs,
    ) -> dict[str, Any]:
        """Create MongoDB connection configuration."""
        if connection_string:
            return {"connection_string": connection_string, **kwargs}

        conn_str = f"mongodb://{username}:{password}@{host}:{port}/{database}"
        return {"connection_string": conn_str, **kwargs}

    @staticmethod
    def create_sqlite_config(database_path: str = "/tmp/test.db", **kwargs) -> dict[str, Any]:
        """Create SQLite connection configuration."""
        config = {"database_path": database_path}
        config.update(kwargs)
        return config

    @staticmethod
    def create_mssql_config(
        host: str = "localhost",
        port: int = 1433,
        database: str = "testdb",
        username: str = "sa",
        password: str = "mssqlpass",
        **kwargs,
    ) -> dict[str, Any]:
        """Create MS SQL Server connection configuration."""
        config = {"host": host, "port": port, "database": database, "username": username, "password": password}
        config.update(kwargs)
        return config

    @staticmethod
    def create_config_for_type(conn_type: str, **kwargs) -> dict[str, Any]:
        """Create connection configuration for specified type."""
        factories = {
            "pg": ConnectionDataFactory.create_pg_config,
            "mysql": ConnectionDataFactory.create_mysql_config,
            "mongo": ConnectionDataFactory.create_mongo_config,
            "sqlite": ConnectionDataFactory.create_sqlite_config,
            "mssql": ConnectionDataFactory.create_mssql_config,
        }

        factory = factories.get(conn_type)
        if not factory:
            raise ValueError(f"Unknown connection type: {conn_type}")

        return factory(**kwargs)


class ConnectionWorkflowHelper:
    """Helper for complex connection workflow scenarios."""

    def __init__(self, connection_helper: ConnectionTestHelper):
        self.connection_helper = connection_helper

    async def setup_multi_environment_connections(
        self, client: AsyncClient, environments: list[str] = None
    ) -> dict[str, dict[str, str]]:
        """
        Set up connections for multiple environments.

        Args:
            client: Test HTTP client
            environments: List of environment names (defaults to dev, staging, prod)

        Returns:
            Dict mapping environment -> connection_type -> connection_id
        """
        if environments is None:
            environments = ["development", "staging", "production"]

        factory = ConnectionDataFactory()
        created = {}

        for env in environments:
            created[env] = {}

            # Create PostgreSQL connection for each environment
            pg_config = factory.create_pg_config(
                host=f"{env}-pg.example.com", database=f"app_{env}", username=f"{env}_user", password=f"{env}_pass_123"
            )
            pg_conn = await self.connection_helper.create_connection(client, "pg", pg_config)
            created[env]["pg"] = pg_conn["id"]

            # Create MongoDB connection for each environment
            mongo_config = factory.create_mongo_config(
                host=f"{env}-mongo.example.com",
                database=f"app_{env}",
                username=f"{env}_mongo",
                password=f"{env}_mongo_pass",
            )
            mongo_conn = await self.connection_helper.create_connection(client, "mongo", mongo_config)
            created[env]["mongo"] = mongo_conn["id"]

        return created

    async def simulate_credential_rotation(
        self, client: AsyncClient, connection_id: str, conn_type: str, num_rotations: int = 3
    ) -> list[dict[str, Any]]:
        """
        Simulate credential rotation for a connection.

        Args:
            client: Test HTTP client
            connection_id: Connection to rotate credentials for
            conn_type: Type of connection
            num_rotations: Number of times to rotate credentials

        Returns:
            List of update responses
        """
        factory = ConnectionDataFactory()
        updates = []

        for i in range(num_rotations):
            new_config = factory.create_config_for_type(conn_type, password=f"RotatedPassword_{i}_{id(self)}")

            updated = await self.connection_helper.update_connection(client, connection_id, conn_type, new_config)
            updates.append(updated)

        return updates


@pytest_asyncio.fixture
async def connection_helper():
    """Provide ConnectionTestHelper instance."""
    return ConnectionTestHelper()


@pytest_asyncio.fixture
async def connection_data_factory():
    """Provide ConnectionDataFactory instance."""
    return ConnectionDataFactory()


@pytest_asyncio.fixture
async def connection_workflow_helper(connection_helper):
    """Provide ConnectionWorkflowHelper instance."""
    return ConnectionWorkflowHelper(connection_helper)


@pytest.fixture
def sample_connection_configs():
    """Provide sample connection configurations for all supported types."""
    factory = ConnectionDataFactory()
    return {
        "pg": factory.create_pg_config(),
        "mysql": factory.create_mysql_config(),
        "mongo": factory.create_mongo_config(),
        "sqlite": factory.create_sqlite_config(),
        "mssql": factory.create_mssql_config(),
    }


@pytest.fixture
def sensitive_connection_data():
    """Provide connection data with sensitive information for encryption testing."""
    return {
        "type": "pg",
        "connection_obj": {
            "host": "secure-db.example.com",
            "port": 5432,
            "database": "sensitive_data",
            "username": "admin_user",
            "password": "SuperSecret123!@#$%",
            "ssl_cert": "-----BEGIN CERTIFICATE-----\nMIIDXTCCAkWgAwIBAgIJAKL...",
            "api_key": "sk-1234567890abcdef",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...",
        },
    }
