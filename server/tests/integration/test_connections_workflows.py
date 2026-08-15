"""
Integration tests for database connections workflows.
Tests complete user journeys and business scenarios for managing database connections.

Schema fetching is mocked via conftest.py so no real external databases are needed.
"""

import asyncio
import base64

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.connections import Connection


@pytest.mark.workflow
@pytest.mark.connection
class TestConnectionCreationWorkflow:
    """Test workflows for creating database connections with different configurations."""

    async def test_create_postgresql_connection_workflow(
        self, test_client: AsyncClient, setup_encryption_key, test_data_factory
    ):
        pg_config = test_data_factory.create_connection(
            "pg",
            host="prod-db.example.com",
            port=5432,
            database="analytics_db",
            username="analytics_user",
            password="SecureP@ssw0rd123",
        )

        response = await test_client.post("/api/connections", json=pg_config)
        assert response.status_code == 201
        connection = response.json()["data"]

        assert connection["id"]
        assert connection["type"] == "pg"
        assert connection["created_at"]

        assert connection.get("connection_obj") is None
        assert "password" not in str(connection)

        list_response = await test_client.get("/api/connections")
        assert list_response.status_code == 200
        connections_list = list_response.json()["data"]

        assert connections_list["total"] == 1
        assert len(connections_list["items"]) == 1
        assert connections_list["items"][0]["id"] == connection["id"]

    async def test_create_multiple_connection_types_workflow(
        self, test_client: AsyncClient, setup_encryption_key, test_data_factory
    ):
        created_connections = []

        connection_configs = [
            test_data_factory.create_connection("pg"),
            test_data_factory.create_connection("mysql"),
            test_data_factory.create_connection("mongo"),
            test_data_factory.create_connection("sqlite"),
            test_data_factory.create_connection("mssql"),
        ]

        for config in connection_configs:
            response = await test_client.post("/api/connections", json=config)
            assert response.status_code == 201
            connection = response.json()["data"]

            assert connection["type"] == config["type"]
            assert connection["id"]
            created_connections.append(connection)

        list_response = await test_client.get("/api/connections")
        assert list_response.status_code == 200
        connections_list = list_response.json()["data"]

        assert connections_list["total"] == 5
        assert len(connections_list["items"]) == 5

        connection_types = {conn["type"] for conn in connections_list["items"]}
        assert connection_types == {"pg", "mysql", "mongo", "sqlite", "mssql"}

    async def test_create_connection_with_missing_type_workflow(self, test_client: AsyncClient):
        invalid_config = {"connection_obj": {"host": "localhost", "port": 5432}}

        response = await test_client.post("/api/connections", json=invalid_config)
        assert response.status_code == 422

    async def test_create_connection_with_invalid_type_workflow(self, test_client: AsyncClient, setup_encryption_key):
        invalid_config = {"type": "unsupported_database", "connection_obj": {"host": "localhost", "port": 9999}}

        response = await test_client.post("/api/connections", json=invalid_config)
        assert response.status_code == 400
        body = response.json()
        assert "Invalid connection type" in (body.get("message") or body.get("detail", ""))

    async def test_create_connection_empty_type_workflow(self, test_client: AsyncClient):
        invalid_config = {"type": "", "connection_obj": {"host": "localhost"}}

        response = await test_client.post("/api/connections", json=invalid_config)
        assert response.status_code == 400
        body = response.json()
        assert "Connection type is required" in (body.get("detail") or body.get("message", ""))


@pytest.mark.workflow
@pytest.mark.connection
class TestConnectionUpdateWorkflow:
    """Test workflows for updating existing database connections."""

    async def test_update_connection_credentials_workflow(
        self, test_client: AsyncClient, setup_encryption_key, test_data_factory
    ):
        initial_config = test_data_factory.create_connection("pg", password="OldPassword123")

        create_response = await test_client.post("/api/connections", json=initial_config)
        assert create_response.status_code == 201
        connection = create_response.json()["data"]
        connection_id = connection["id"]

        updated_config = test_data_factory.create_connection(
            "pg", password="NewSecureP@ssw0rd456", host="new-prod-db.example.com", database="new_analytics_db"
        )

        update_response = await test_client.put(f"/api/connections/{connection_id}", json=updated_config)
        assert update_response.status_code == 200
        updated_connection = update_response.json()["data"]

        assert updated_connection["id"] == connection_id
        assert updated_connection["type"] == "pg"

        assert updated_connection.get("connection_obj") is None
        assert "password" not in str(updated_connection)

    async def test_update_connection_type_workflow(
        self, test_client: AsyncClient, setup_encryption_key, test_data_factory
    ):
        pg_config = test_data_factory.create_connection("pg")

        create_response = await test_client.post("/api/connections", json=pg_config)
        assert create_response.status_code == 201
        connection_id = create_response.json()["data"]["id"]

        mysql_config = test_data_factory.create_connection("mysql")

        update_response = await test_client.put(f"/api/connections/{connection_id}", json=mysql_config)
        assert update_response.status_code == 200
        updated_connection = update_response.json()["data"]

        assert updated_connection["type"] == "mysql"
        assert updated_connection["id"] == connection_id

    async def test_update_nonexistent_connection_workflow(self, test_client: AsyncClient, test_data_factory):
        fake_id = "00000000-0000-0000-0000-000000000000"
        config = test_data_factory.create_connection("pg")

        response = await test_client.put(f"/api/connections/{fake_id}", json=config)
        assert response.status_code == 404
        body = response.json()
        assert "Connection not found" in (body.get("detail") or body.get("message", ""))


@pytest.mark.workflow
@pytest.mark.connection
class TestConnectionListingWorkflow:
    """Test workflows for listing and filtering database connections."""

    async def test_list_empty_connections_workflow(self, test_client: AsyncClient):
        response = await test_client.get("/api/connections")
        assert response.status_code == 200

        data = response.json()["data"]
        if isinstance(data, dict):
            assert data.get("total", 0) == 0 or data.get("items", []) == []
        elif isinstance(data, list):
            assert len(data) == 0

    async def test_list_connections_pagination_workflow(
        self, test_client: AsyncClient, setup_encryption_key, test_data_factory
    ):
        num_connections = 10
        created_ids = []

        for i in range(num_connections):
            config = test_data_factory.create_connection("pg" if i % 2 == 0 else "mysql", database=f"database_{i}")
            response = await test_client.post("/api/connections", json=config)
            assert response.status_code == 201
            created_ids.append(response.json()["data"]["id"])

        list_response = await test_client.get("/api/connections")
        assert list_response.status_code == 200
        connections_list = list_response.json()["data"]

        assert connections_list["total"] == num_connections
        assert len(connections_list["items"]) == num_connections

        listed_ids = {conn["id"] for conn in connections_list["items"]}
        assert set(created_ids) == listed_ids


@pytest.mark.workflow
@pytest.mark.connection
class TestConnectionEncryptionWorkflow:
    """Test workflows related to connection encryption and security."""

    async def test_connection_encryption_persistence_workflow(
        self, test_client: AsyncClient, test_session: AsyncSession, setup_encryption_key, test_data_factory
    ):
        sensitive_config = test_data_factory.create_connection(
            "pg", password="SuperSecret123!@#", username="admin_user"
        )

        response = await test_client.post("/api/connections", json=sensitive_config)
        assert response.status_code == 201
        connection_id = response.json()["data"]["id"]

        result = await test_session.execute(select(Connection).where(Connection.id == connection_id))
        db_connection = result.scalar_one()

        assert "SuperSecret123!@#" not in db_connection.connection_obj_encrypted
        assert "admin_user" not in db_connection.connection_obj_encrypted

        try:
            base64.b64decode(db_connection.connection_obj_encrypted)
            is_base64 = True
        except Exception:
            is_base64 = False
        assert is_base64

        decrypted = await db_connection.get_decrypted_connection_obj(test_session)
        assert decrypted["password"] == "SuperSecret123!@#"
        assert decrypted["username"] == "admin_user"


@pytest.mark.workflow
@pytest.mark.connection
@pytest.mark.error_handling
class TestConnectionErrorHandlingWorkflow:
    """Test error handling workflows for connection management."""

    async def test_concurrent_connection_creation_workflow(
        self, test_client: AsyncClient, setup_encryption_key, test_data_factory
    ):
        configs = [test_data_factory.create_connection("pg", database=f"db_{i}") for i in range(5)]

        tasks = [test_client.post("/api/connections", json=config) for config in configs]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for response in responses:
            assert not isinstance(response, Exception)
            assert response.status_code == 201

        list_response = await test_client.get("/api/connections")
        assert list_response.json()["data"]["total"] == 5

    async def test_malformed_connection_object_workflow(self, test_client: AsyncClient, setup_encryption_key):
        invalid_configs = [
            {"type": "pg", "connection_obj": "not a dictionary"},
            {"type": "pg", "connection_obj": ["list", "instead", "of", "dict"]},
            {"type": "pg", "connection_obj": None},
        ]

        for config in invalid_configs:
            response = await test_client.post("/api/connections", json=config)
            assert response.status_code in [400, 422]


@pytest.mark.workflow
@pytest.mark.connection
class TestConnectionBusinessWorkflows:
    """Test real-world business workflows involving connections."""

    async def test_database_migration_workflow(self, test_client: AsyncClient, setup_encryption_key, test_data_factory):
        old_db_config = test_data_factory.create_connection(
            "pg", host="legacy-db.example.com", database="legacy_app", username="legacy_user", password="LegacyPass123"
        )

        old_response = await test_client.post("/api/connections", json=old_db_config)
        assert old_response.status_code == 201
        old_connection_id = old_response.json()["data"]["id"]

        new_db_config = test_data_factory.create_connection(
            "pg", host="modern-db.example.com", database="modern_app", username="modern_user", password="ModernPass456"
        )

        new_response = await test_client.post("/api/connections", json=new_db_config)
        assert new_response.status_code == 201
        new_connection_id = new_response.json()["data"]["id"]

        list_response = await test_client.get("/api/connections")
        connections = list_response.json()["data"]
        assert connections["total"] >= 2

        connection_ids = {conn["id"] for conn in connections["items"]}
        assert old_connection_id in connection_ids
        assert new_connection_id in connection_ids

        deprecated_config = test_data_factory.create_connection(
            "pg",
            host="archive-db.example.com",
            database="archived_legacy",
            username="archive_user",
            password="ArchivePass789",
        )

        update_response = await test_client.put(f"/api/connections/{old_connection_id}", json=deprecated_config)
        assert update_response.status_code == 200

    async def test_multi_environment_setup_workflow(
        self, test_client: AsyncClient, setup_encryption_key, test_data_factory
    ):
        environments = {
            "development": {
                "pg": test_data_factory.create_connection("pg", host="dev-pg.local", database="app_dev"),
                "mongo": test_data_factory.create_connection(
                    "mongo", connection_string="mongodb://dev:devpass@dev-mongo.local:27017/app_dev"
                ),
            },
            "staging": {
                "pg": test_data_factory.create_connection("pg", host="staging-pg.example.com", database="app_staging"),
                "mongo": test_data_factory.create_connection(
                    "mongo", connection_string="mongodb://staging:stagepass@staging-mongo.example.com:27017/app_staging"
                ),
            },
            "production": {
                "pg": test_data_factory.create_connection(
                    "pg", host="prod-pg.example.com", database="app_prod", password="SuperSecureProdPassword123!@#"
                ),
                "mongo": test_data_factory.create_connection(
                    "mongo", connection_string="mongodb://prod:prodpass@prod-mongo.example.com:27017/app_prod"
                ),
            },
        }

        created_connections = {}

        for env_name, env_configs in environments.items():
            created_connections[env_name] = {}
            for db_type, config in env_configs.items():
                response = await test_client.post("/api/connections", json=config)
                assert response.status_code == 201
                created_connections[env_name][db_type] = response.json()["data"]["id"]

        list_response = await test_client.get("/api/connections")
        connections = list_response.json()["data"]
        assert connections["total"] == 6

        type_counts = {}
        for conn in connections["items"]:
            type_counts[conn["type"]] = type_counts.get(conn["type"], 0) + 1

        assert type_counts["pg"] == 3
        assert type_counts["mongo"] == 3

    async def test_connection_rotation_workflow(
        self, test_client: AsyncClient, setup_encryption_key, test_data_factory
    ):
        initial_config = test_data_factory.create_connection(
            "mysql", username="app_user", password="InitialPassword123"
        )

        create_response = await test_client.post("/api/connections", json=initial_config)
        assert create_response.status_code == 201
        connection_id = create_response.json()["data"]["id"]

        rotation_passwords = ["RotatedPassword456", "RotatedPassword789", "FinalRotatedPassword000"]

        for new_password in rotation_passwords:
            rotated_config = test_data_factory.create_connection("mysql", username="app_user", password=new_password)

            update_response = await test_client.put(f"/api/connections/{connection_id}", json=rotated_config)
            assert update_response.status_code == 200

            list_response = await test_client.get("/api/connections")
            connection_ids = {conn["id"] for conn in list_response.json()["data"]["items"]}
            assert connection_id in connection_ids
