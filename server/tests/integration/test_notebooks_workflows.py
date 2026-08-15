"""
Integration tests for notebook workflows.
Tests complete user journeys and business scenarios for the notebooks feature.

Schema fetching is mocked via conftest.py so no real external databases are needed.
"""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fixtures.notebooks_fixtures import ConnectionTestHelper, NotebookTestHelper, WorkflowTestHelper


@pytest.mark.workflow
@pytest.mark.notebook
class TestNotebookCreationAndManagementWorkflow:
    """Test notebook creation and management workflows."""

    async def test_create_notebook_with_valid_data(self, test_client: AsyncClient, notebook_helper: NotebookTestHelper):
        notebook = await notebook_helper.create_notebook(
            test_client, name="Data Analysis Project", description="Q4 2024 Sales Analysis"
        )

        assert notebook["id"]
        assert notebook["notebook_name"] == "Data Analysis Project"
        assert notebook["description"] == "Q4 2024 Sales Analysis"
        assert notebook["created_at"]
        assert notebook["updated_at"]

    async def test_create_notebook_with_minimal_data(self, test_client: AsyncClient):
        response = await test_client.post("/api/notebooks", json={"notebook_name": "Minimal Notebook"})

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["notebook_name"] == "Minimal Notebook"
        assert data.get("description") is None

    async def test_create_notebook_missing_required_fields(self, test_client: AsyncClient):
        response = await test_client.post("/api/notebooks", json={"description": "Missing name"})

        assert response.status_code == 422

    async def test_list_all_notebooks(self, test_client: AsyncClient, notebook_helper: NotebookTestHelper):
        notebooks = []
        for i in range(3):
            notebook = await notebook_helper.create_notebook(test_client, name=f"Notebook {i + 1}")
            notebooks.append(notebook)

        response = await notebook_helper.list_notebooks(test_client)

        assert "items" in response
        assert "total" in response
        assert response["total"] == 3
        assert len(response["items"]) == 3

        notebook_ids = {n["id"] for n in notebooks}
        listed_ids = {n["id"] for n in response["items"]}
        assert notebook_ids == listed_ids

    async def test_delete_notebook_and_cascade(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
        notebook_helper: NotebookTestHelper,
        workflow_helper: WorkflowTestHelper,
        setup_encryption_key,
        sample_pg_connection: dict,
    ):
        notebook = await notebook_helper.create_notebook(test_client, name="Notebook to Delete")
        notebook_id = notebook["id"]

        await notebook_helper.connect_with_new_connection(
            test_client, notebook_id, sample_pg_connection["type"], sample_pg_connection["connection_obj"]
        )

        connections = await notebook_helper.get_notebook_connections(test_client, notebook_id)
        assert len(connections) >= 1

        await notebook_helper.delete_notebook(test_client, notebook_id)

        remaining = await workflow_helper.verify_cascade_deletion(test_session, notebook_id)

        assert remaining["notebook_datasets"] == 0
        assert remaining["threads"] == 0
        assert remaining["datasets"] == 0

    async def test_delete_nonexistent_notebook(self, test_client: AsyncClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await test_client.delete(f"/api/notebooks/{fake_id}")
        assert response.status_code == 404


@pytest.mark.workflow
@pytest.mark.connection
class TestDatabaseConnectionWorkflow:
    """Test database connection workflows."""

    async def test_create_new_connection_while_connecting(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
        setup_encryption_key,
        sample_notebook: dict,
        sample_pg_connection: dict,
        connection_helper: ConnectionTestHelper,
    ):
        notebook_id = sample_notebook["id"]

        response = await test_client.post(
            f"/api/notebooks/{notebook_id}/connections", json={"connection": sample_pg_connection}
        )

        assert response.status_code == 201
        data = response.json()["data"]

        assert "dataset" in data or "notebook_connection" in data
        assert "connection" in data
        assert data["connection"]["type"] == "pg"

    async def test_connect_to_existing_connection(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
        setup_encryption_key,
        sample_notebook: dict,
        sample_pg_connection: dict,
        connection_helper: ConnectionTestHelper,
    ):
        notebook_id = sample_notebook["id"]

        connection_id = await connection_helper.create_connection(
            test_session, sample_pg_connection["type"], sample_pg_connection["connection_obj"]
        )

        response = await test_client.post(
            f"/api/notebooks/{notebook_id}/connections", json={"connection_id": connection_id}
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["connection"]["id"] == connection_id

    async def test_invalid_connection_attempt_missing_data(self, test_client: AsyncClient, sample_notebook: dict):
        notebook_id = sample_notebook["id"]

        response = await test_client.post(f"/api/notebooks/{notebook_id}/connections", json={})

        assert response.status_code == 400
        assert "Either connection_id or connection details are required" in (
            response.json().get("detail") or response.json().get("message", "")
        )

    async def test_invalid_connection_type(
        self, test_client: AsyncClient, test_session: AsyncSession, setup_encryption_key, sample_notebook: dict
    ):
        notebook_id = sample_notebook["id"]

        response = await test_client.post(
            f"/api/notebooks/{notebook_id}/connections",
            json={"connection": {"type": "invalid_db", "connection_obj": {"some": "data"}}},
        )

        assert response.status_code == 400
        assert "Invalid connection type" in (response.json().get("detail") or response.json().get("message", ""))

    async def test_connect_to_nonexistent_notebook(self, test_client: AsyncClient, sample_pg_connection: dict):
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await test_client.post(
            f"/api/notebooks/{fake_id}/connections", json={"connection": sample_pg_connection}
        )

        assert response.status_code == 404
        assert "Notebook not found" in (response.json().get("detail") or response.json().get("message", ""))

    async def test_connect_to_nonexistent_connection(self, test_client: AsyncClient, sample_notebook: dict):
        notebook_id = sample_notebook["id"]
        fake_connection_id = "00000000-0000-0000-0000-000000000000"

        response = await test_client.post(
            f"/api/notebooks/{notebook_id}/connections", json={"connection_id": fake_connection_id}
        )

        assert response.status_code == 404
        assert "Connection not found" in (response.json().get("detail") or response.json().get("message", ""))


@pytest.mark.workflow
class TestMultipleConnectionsWorkflow:
    """Test workflows involving multiple database connections."""

    async def test_connect_notebook_to_multiple_databases(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
        setup_encryption_key,
        sample_notebook: dict,
        sample_pg_connection: dict,
        sample_mongo_connection: dict,
        sample_sqlite_connection: dict,
        notebook_helper: NotebookTestHelper,
    ):
        notebook_id = sample_notebook["id"]

        await notebook_helper.connect_with_new_connection(
            test_client, notebook_id, sample_pg_connection["type"], sample_pg_connection["connection_obj"]
        )

        await notebook_helper.connect_with_new_connection(
            test_client, notebook_id, sample_mongo_connection["type"], sample_mongo_connection["connection_obj"]
        )

        await notebook_helper.connect_with_new_connection(
            test_client, notebook_id, sample_sqlite_connection["type"], sample_sqlite_connection["connection_obj"]
        )

        connections = await notebook_helper.get_notebook_connections(test_client, notebook_id)
        assert len(connections) == 3

    async def test_get_notebook_connections_list(
        self, test_client: AsyncClient, notebook_with_connections: dict, notebook_helper: NotebookTestHelper
    ):
        notebook_id = notebook_with_connections["notebook_id"]

        connections = await notebook_helper.get_notebook_connections(test_client, notebook_id)

        assert len(connections) == 2
        for conn in connections:
            assert "id" in conn
            assert "notebook_id" in conn

    async def test_get_notebook_connections_with_decrypted_details(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
        setup_encryption_key,
        sample_notebook: dict,
        sample_pg_connection: dict,
        notebook_helper: NotebookTestHelper,
    ):
        notebook_id = sample_notebook["id"]

        await notebook_helper.connect_with_new_connection(
            test_client, notebook_id, sample_pg_connection["type"], sample_pg_connection["connection_obj"]
        )

        connections = await notebook_helper.get_notebook_connections_with_details(test_client, notebook_id)

        assert len(connections) >= 1
        conn = connections[0]

        assert conn["type"] == "pg"
        assert "connection_obj" in conn

    async def test_multiple_notebooks_share_connection(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
        setup_encryption_key,
        sample_pg_connection: dict,
        notebook_helper: NotebookTestHelper,
        connection_helper: ConnectionTestHelper,
    ):
        notebook1 = await notebook_helper.create_notebook(test_client, name="Analysis Project 1")
        notebook2 = await notebook_helper.create_notebook(test_client, name="Analysis Project 2")

        connection_id = await connection_helper.create_connection(
            test_session, sample_pg_connection["type"], sample_pg_connection["connection_obj"]
        )

        await notebook_helper.connect_to_existing_connection(test_client, notebook1["id"], connection_id)
        await notebook_helper.connect_to_existing_connection(test_client, notebook2["id"], connection_id)

        notebook1_conns = await notebook_helper.get_notebook_connections(test_client, notebook1["id"])
        notebook2_conns = await notebook_helper.get_notebook_connections(test_client, notebook2["id"])

        assert len(notebook1_conns) >= 1
        assert len(notebook2_conns) >= 1


@pytest.mark.workflow
class TestEndToEndDataAnalysisWorkflow:
    """Test complete end-to-end data analysis workflows."""

    async def test_complete_analysis_project_setup(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
        setup_encryption_key,
        workflow_helper: WorkflowTestHelper,
        test_data_factory,
    ):
        databases = [
            test_data_factory.create_connection("pg", database="sales_db"),
            test_data_factory.create_connection("mongo", database="customer_db"),
            test_data_factory.create_connection("mysql", database="inventory_db"),
        ]

        project = await workflow_helper.setup_analysis_project(test_client, "Multi-Source Sales Analysis", databases)

        assert project["notebook_id"]
        assert len(project["connection_ids"]) == 3
        assert project["notebook"]["notebook_name"] == "Multi-Source Sales Analysis"

        connections = await NotebookTestHelper.get_notebook_connections_with_details(
            test_client, project["notebook_id"]
        )

        assert len(connections) == 3

        connection_types = {conn["type"] for conn in connections}
        assert connection_types == {"pg", "mongo", "mysql"}

    async def test_analysis_workflow_with_connection_updates(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
        setup_encryption_key,
        sample_notebook: dict,
        test_data_factory,
        notebook_helper: NotebookTestHelper,
    ):
        notebook_id = sample_notebook["id"]

        pg_conn = test_data_factory.create_connection("pg", database="primary_db")
        await notebook_helper.connect_with_new_connection(
            test_client, notebook_id, pg_conn["type"], pg_conn["connection_obj"]
        )

        connections = await notebook_helper.get_notebook_connections(test_client, notebook_id)
        assert len(connections) == 1

        mongo_conn = test_data_factory.create_connection("mongo", database="secondary_db")
        await notebook_helper.connect_with_new_connection(
            test_client, notebook_id, mongo_conn["type"], mongo_conn["connection_obj"]
        )

        sqlite_conn = test_data_factory.create_connection("sqlite", database_path="/tmp/cache.db")
        await notebook_helper.connect_with_new_connection(
            test_client, notebook_id, sqlite_conn["type"], sqlite_conn["connection_obj"]
        )

        final_connections = await notebook_helper.get_notebook_connections_with_details(test_client, notebook_id)

        assert len(final_connections) == 3

        db_types = [conn["type"] for conn in final_connections]
        assert "pg" in db_types
        assert "mongo" in db_types
        assert "sqlite" in db_types

    async def test_project_cleanup_workflow(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
        setup_encryption_key,
        workflow_helper: WorkflowTestHelper,
        notebook_helper: NotebookTestHelper,
        test_data_factory,
    ):
        projects = []
        for i in range(3):
            project = await workflow_helper.setup_analysis_project(
                test_client,
                f"Project {i + 1}",
                [test_data_factory.create_connection("pg"), test_data_factory.create_connection("mongo")],
            )
            projects.append(project)

        all_notebooks = await notebook_helper.list_notebooks(test_client)
        assert all_notebooks["total"] >= 3

        await notebook_helper.delete_notebook(test_client, projects[0]["notebook_id"])

        remaining = await workflow_helper.verify_cascade_deletion(test_session, projects[0]["notebook_id"])
        assert all(count == 0 for count in remaining.values())

        notebooks_after = await notebook_helper.list_notebooks(test_client)
        remaining_ids = {n["id"] for n in notebooks_after["items"]}

        assert projects[1]["notebook_id"] in remaining_ids
        assert projects[2]["notebook_id"] in remaining_ids
        assert projects[0]["notebook_id"] not in remaining_ids


@pytest.mark.workflow
@pytest.mark.error_handling
class TestErrorHandlingWorkflows:
    """Test error handling in various workflow scenarios."""

    async def test_handle_nonexistent_notebook_operations(self, test_client: AsyncClient):
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await test_client.get(f"/api/notebooks/{fake_id}/connections")
        assert response.status_code == 404
        assert "Notebook not found" in (response.json().get("detail") or response.json().get("message", ""))

        response = await test_client.get(f"/api/notebooks/{fake_id}/connections/details")
        assert response.status_code == 404
        assert "Notebook not found" in (response.json().get("detail") or response.json().get("message", ""))

    async def test_handle_invalid_connection_types(
        self, test_client: AsyncClient, test_session: AsyncSession, setup_encryption_key, sample_notebook: dict
    ):
        notebook_id = sample_notebook["id"]

        invalid_types = ["redis", "elasticsearch", ""]

        for invalid_type in invalid_types:
            response = await test_client.post(
                f"/api/notebooks/{notebook_id}/connections",
                json={"connection": {"type": invalid_type, "connection_obj": {"some": "config"}}},
            )
            assert response.status_code == 400
            assert "Invalid connection type" in (response.json().get("detail") or response.json().get("message", ""))

    async def test_handle_malformed_connection_data(self, test_client: AsyncClient, sample_notebook: dict):
        notebook_id = sample_notebook["id"]

        response = await test_client.post(
            f"/api/notebooks/{notebook_id}/connections", json={"connection": {"type": "pg", "connection_obj": None}}
        )
        assert response.status_code in [201, 422, 500]

    async def test_concurrent_notebook_operations(
        self,
        test_client: AsyncClient,
        test_session: AsyncSession,
        setup_encryption_key,
        notebook_helper: NotebookTestHelper,
    ):
        notebook = await notebook_helper.create_notebook(test_client, name="Concurrent Test Notebook")
        notebook_id = notebook["id"]

        async def add_connection(conn_type: str, index: int):
            if conn_type == "mongo":
                connection_config = {
                    "connection_string": f"mongodb://user{index}:pass{index}@host{index}:27017/db{index}"
                }
            elif conn_type == "sqlite":
                connection_config = {"database_path": f"/tmp/db{index}.db"}
            else:
                connection_config = {
                    "host": f"host{index}",
                    "database": f"db{index}",
                    "username": f"user{index}",
                    "password": f"pass{index}",
                }

            return await test_client.post(
                f"/api/notebooks/{notebook_id}/connections",
                json={"connection": {"type": conn_type, "connection_obj": connection_config}},
            )

        tasks = [add_connection("pg", 1), add_connection("mysql", 2), add_connection("mongo", 3)]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        for response in responses:
            if not isinstance(response, Exception) and response.status_code == 201:
                success_count += 1

        assert success_count >= 1

        connections = await notebook_helper.get_notebook_connections(test_client, notebook_id)
        assert len(connections) >= 1

    async def test_validation_errors_in_workflow(self, test_client: AsyncClient):
        invalid_payloads = [
            {},
            {"notebook_name": ""},
            {"notebook_name": None},
            {"notebook_name": 123},
        ]

        for payload in invalid_payloads:
            response = await test_client.post("/api/notebooks", json=payload)
            if response.status_code not in [400, 422]:
                assert response.status_code == 201
            else:
                error_data = response.json()
                assert "detail" in error_data or "message" in error_data
