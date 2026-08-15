"""
Reusable fixtures for notebook integration tests.
Provides utilities for creating and managing test notebooks and connections.
"""

import json
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.connections import Connection
from server.models.notebooks import NotebookDataset
from server.models.threads import Thread
from server.repositories.connections import ConnectionRepository


class NotebookTestHelper:
    """Helper class for notebook-related test operations."""

    @staticmethod
    async def create_notebook(client: AsyncClient, name: str = None, description: str = None) -> dict:
        """Create a notebook via API and return the response data."""
        payload = {
            "notebook_name": name or f"Test Notebook {uuid.uuid4().hex[:8]}",
            "description": description or "Test notebook description",
        }
        response = await client.post("/api/notebooks", json=payload)
        if response.status_code != 201:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
        assert response.status_code == 201
        return response.json()["data"]

    @staticmethod
    async def list_notebooks(client: AsyncClient) -> dict:
        response = await client.get("/api/notebooks")
        assert response.status_code == 200
        return response.json()["data"]

    @staticmethod
    async def delete_notebook(client: AsyncClient, notebook_id: str) -> None:
        response = await client.delete(f"/api/notebooks/{notebook_id}")
        assert response.status_code == 204

    @staticmethod
    async def connect_to_existing_connection(client: AsyncClient, notebook_id: str, connection_id: str) -> dict:
        payload = {"connection_id": connection_id}
        response = await client.post(f"/api/notebooks/{notebook_id}/connections", json=payload)
        assert response.status_code == 201
        return response.json()["data"]

    @staticmethod
    async def connect_with_new_connection(
        client: AsyncClient, notebook_id: str, connection_type: str, connection_obj: dict
    ) -> dict:
        payload = {"connection": {"type": connection_type, "connection_obj": connection_obj}}
        response = await client.post(f"/api/notebooks/{notebook_id}/connections", json=payload)
        assert response.status_code == 201
        return response.json()["data"]

    @staticmethod
    async def get_notebook_connections(client: AsyncClient, notebook_id: str) -> list[dict]:
        response = await client.get(f"/api/notebooks/{notebook_id}/connections")
        assert response.status_code == 200
        return response.json()["data"]

    @staticmethod
    async def get_notebook_connections_with_details(client: AsyncClient, notebook_id: str) -> list[dict]:
        response = await client.get(f"/api/notebooks/{notebook_id}/connections/details")
        assert response.status_code == 200
        return response.json()["data"]


class ConnectionTestHelper:
    """Helper class for connection-related test operations."""

    @staticmethod
    async def create_connection(session: AsyncSession, conn_type: str, connection_obj: dict) -> str:
        from sqlalchemy import select

        from server.models.tenant import Tenant

        result = await session.execute(select(Tenant).limit(1))
        tenant = result.scalar_one()

        connection = Connection(type=conn_type, tenant_id=tenant.id)
        await connection.set_encrypted_connection_obj(connection_obj, session)
        session.add(connection)
        await session.commit()
        await session.refresh(connection)
        return str(connection.id)

    @staticmethod
    async def verify_connection_encryption(session: AsyncSession, connection_id: str, expected_obj: dict) -> bool:
        """Verify that a connection's data is properly encrypted and can be decrypted."""
        conn_repo = ConnectionRepository(session)
        connection = await conn_repo.get(connection_id)

        if not connection:
            return False

        # Check that the stored data is encrypted (not plain JSON)
        try:
            # If this succeeds, the data is NOT encrypted (bad)
            json.loads(connection.connection_obj_encrypted)
            return False
        except (json.JSONDecodeError, TypeError):
            # Good, data is encrypted
            pass

        # Verify decryption works and returns expected data
        decrypted = await connection.get_decrypted_connection_obj(session)
        return decrypted == expected_obj


class WorkflowTestHelper:
    """Helper class for testing complete workflows."""

    @staticmethod
    async def setup_analysis_project(client: AsyncClient, project_name: str, databases: list[dict[str, any]]) -> dict:
        """
        Set up a complete analysis project with notebook and multiple connections.

        Args:
            client: Test HTTP client
            project_name: Name for the notebook
            databases: List of database configurations, each with 'type' and 'connection_obj'

        Returns:
            Dictionary with notebook_id and list of connection_ids
        """
        # Create notebook
        notebook = await NotebookTestHelper.create_notebook(
            client, name=project_name, description=f"Analysis project: {project_name}"
        )
        notebook_id = notebook["id"]

        # Connect to all databases
        connection_ids = []
        for db_config in databases:
            response = await NotebookTestHelper.connect_with_new_connection(
                client, notebook_id, db_config["type"], db_config["connection_obj"]
            )
            connection_ids.append(response["connection"]["id"])

        return {"notebook_id": notebook_id, "connection_ids": connection_ids, "notebook": notebook}

    @staticmethod
    async def verify_cascade_deletion(session: AsyncSession, notebook_id: str) -> dict:
        """
        Verify that deleting a notebook cascades to all related entities.

        Returns:
            Dictionary with counts of remaining related entities (should all be 0)
        """
        # Count remaining related entities
        notebook_datasets = await session.scalar(
            select(func.count()).select_from(NotebookDataset).where(NotebookDataset.notebook_id == notebook_id)
        )

        threads = await session.scalar(
            select(func.count()).select_from(Thread).where(Thread.notebook_id == notebook_id)
        )

        return {
            "notebook_datasets": notebook_datasets or 0,
            "threads": threads or 0,
            "datasets": 0,  # Kept for backward compatibility with tests
        }


@pytest.fixture
def notebook_helper():
    """Provide notebook test helper instance."""
    return NotebookTestHelper()


@pytest.fixture
def connection_helper():
    """Provide connection test helper instance."""
    return ConnectionTestHelper()


@pytest.fixture
def workflow_helper():
    """Provide workflow test helper instance."""
    return WorkflowTestHelper()


@pytest_asyncio.fixture
async def sample_notebook(test_client: AsyncClient) -> dict:
    """Create a sample notebook for testing."""
    notebook = await NotebookTestHelper.create_notebook(
        test_client, name="Sample Test Notebook", description="A notebook created for testing"
    )
    yield notebook
    # Cleanup is handled by database teardown


@pytest_asyncio.fixture
async def notebook_with_connections(
    test_client: AsyncClient, sample_pg_connection: dict, sample_mongo_connection: dict
) -> dict:
    """Create a notebook with multiple database connections."""
    result = await WorkflowTestHelper.setup_analysis_project(
        test_client, "Multi-DB Analysis Project", [sample_pg_connection, sample_mongo_connection]
    )
    yield result
    # Cleanup is handled by database teardown
