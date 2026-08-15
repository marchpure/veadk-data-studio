from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.tenant_context import get_tenant_id
from server.models.notebooks import Notebook
from server.repositories import NotebookRepository
from server.repositories.dashboard import DashboardRepository
from server.repositories.queries import QueryRepository
from server.repositories.threads import ThreadRepository
from server.schemas.notebooks import NotebookCreate, NotebookUpdate
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class NotebookService:
    @staticmethod
    async def create_notebook(
        session: AsyncSession,
        payload: NotebookCreate,
        tenant_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> Notebook:
        try:
            # Use tenant_id from context if not explicitly provided
            effective_tenant_id = tenant_id or get_tenant_id()

            repo = NotebookRepository(session)
            create_data = {
                "notebook_name": payload.notebook_name,
                "description": payload.description,
            }
            # Add tenant_id and created_by if provided
            if effective_tenant_id:
                create_data["tenant_id"] = effective_tenant_id
            if user_id:
                create_data["created_by"] = user_id

            notebook = await repo.create(create_data)

            thread_repo = ThreadRepository(session)
            await thread_repo.create(
                {
                    "id": notebook.id,
                    "notebook_id": notebook.id,
                    "thread_title": None,
                }
            )

            # Create initial dashboard HTML in database with template
            dashboard_repo = DashboardRepository(session)
            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{payload.notebook_name} - Dashboard</title>

  <!-- CRITICAL: All CDN scripts in HEAD (order matters) -->
  <script crossorigin src="https://unpkg.com/react@17.0.2/umd/react.development.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@17.0.2/umd/react-dom.development.js"></script>
  <script crossorigin src="https://unpkg.com/prop-types@15.8.1/prop-types.min.js"></script>
  <script crossorigin src="https://cdnjs.cloudflare.com/ajax/libs/recharts/2.15.4/Recharts.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone@7.23.9/babel.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body>
  <!-- CRITICAL: <div id="root"></div> MUST exist BEFORE <script> tag -->
  <div id="root"></div>

  <script type="text/babel">
    // CRITICAL: waitForDependencies function MUST be at top
    const waitForDependencies = () => {{
      return new Promise((resolve) => {{
        const check = () => {{
          if (window.React && window.ReactDOM && window.PropTypes && window.Recharts) {{
            resolve();
          }} else {{
            setTimeout(check, 100);
          }}
        }};
        check();
      }});
    }};

    // Dashboard component definition
    const Dashboard = () => {{
      const [ready, setReady] = React.useState(false);

      React.useEffect(() => {{
        waitForDependencies().then(() => setReady(true));
      }}, []);

      if (!ready) {{
        return React.createElement('div', {{
          className: 'flex items-center justify-center h-screen bg-gradient-to-br from-blue-50 to-indigo-100'
        }}, React.createElement('div', {{
          className: 'text-2xl font-bold text-indigo-600'
        }}, 'Loading dashboard...'));
      }}

      return (
        <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 p-8">
          <div className="max-w-7xl mx-auto">
            {{/* Header */}}
            <div className="text-center mb-8">
              <h1 className="text-5xl font-black bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent mb-2">
                {payload.notebook_name}
              </h1>
              <p className="text-lg text-gray-600 font-medium">
                Your interactive dashboard
              </p>
            </div>

            {{/* Placeholder Content Area */}}
            <div className="bg-white rounded-2xl shadow-xl p-12 border border-gray-100 text-center">
              <div className="text-6xl mb-4">📊</div>
              <h2 className="text-3xl font-bold text-gray-800 mb-4">Data Here</h2>
              <p className="text-lg text-gray-600 mb-6">
                Use the code assistant to generate interactive visualizations and data displays for your dashboard.
              </p>
              <div className="inline-block bg-gradient-to-r from-blue-100 to-purple-100 border-2 border-blue-300 rounded-lg p-4 text-sm text-gray-700">
                Your dashboard content will appear here once you add visualizations and components.
              </div>
            </div>
          </div>
        </div>
      );
    }};

    // CRITICAL: ReactDOM.render at VERY END, after waitForDependencies
    waitForDependencies().then(() => {{
      const root = document.getElementById('root');
      if (root) ReactDOM.render(React.createElement(Dashboard), root);
    }});
  </script>
</body>
</html>"""
            await dashboard_repo.create_with_version(notebook.id, html_content, effective_tenant_id)

            return notebook
        except Exception as e:
            logger.error(
                f"Failed to create notebook: {str(e)}",
                posthog_context={"function": "NotebookService.create_notebook", "notebook_name": payload.notebook_name},
            )
            raise

    @staticmethod
    async def get_notebook(
        session: AsyncSession,
        notebook_id: str,
    ) -> Notebook | None:
        try:
            repo = NotebookRepository(session)
            notebook = await repo.get(notebook_id)
            return notebook
        except Exception as e:
            logger.error(
                f"Failed to get notebook: {str(e)}",
                posthog_context={"function": "NotebookService.get_notebook", "notebook_id": notebook_id},
            )
            raise

    @staticmethod
    async def list_notebooks(
        session: AsyncSession,
    ) -> list[Notebook]:
        try:
            repo = NotebookRepository(session)
            notebooks = await repo.list_all()
            return notebooks
        except Exception as e:
            logger.error(
                f"Failed to list notebooks: {str(e)}", posthog_context={"function": "NotebookService.list_notebooks"}
            )
            raise

    @staticmethod
    async def update_notebook(
        session: AsyncSession,
        notebook_id: str,
        payload: NotebookUpdate,
    ) -> Notebook | None:
        try:
            repo = NotebookRepository(session)
            update_data = {}
            if payload.notebook_name is not None:
                update_data["notebook_name"] = payload.notebook_name
            if payload.description is not None:
                update_data["description"] = payload.description
            if payload.last_used_provider is not None:
                update_data["last_used_provider"] = payload.last_used_provider
            if payload.last_used_model is not None:
                update_data["last_used_model"] = payload.last_used_model

            if not update_data:
                return await repo.get(notebook_id)

            return await repo.update(notebook_id, update_data)
        except Exception as e:
            logger.error(
                f"Failed to update notebook: {str(e)}",
                posthog_context={"function": "NotebookService.update_notebook", "notebook_id": notebook_id},
            )
            raise

    @staticmethod
    async def delete_notebook(
        session: AsyncSession,
        notebook_id: str,
    ) -> bool:
        try:
            repo = NotebookRepository(session)
            return await repo.delete(notebook_id)
        except Exception as e:
            logger.error(
                f"Failed to delete notebook: {str(e)}",
                posthog_context={"function": "NotebookService.delete_notebook", "notebook_id": notebook_id},
            )
            raise

    @staticmethod
    async def get_notebook_html_content(
        session: AsyncSession, notebook_id: str, version: int | None = None
    ) -> str | None:
        """Get the HTML content from the database for a notebook."""
        try:
            dashboard_repo = DashboardRepository(session)
            if version is not None:
                dashboard = await dashboard_repo.get_version(notebook_id, version)
            else:
                dashboard = await dashboard_repo.get_latest_version(notebook_id)
            if dashboard:
                return dashboard.html_content
            return None
        except Exception as e:
            logger.error(f"Failed to read HTML content for notebook {notebook_id}: {str(e)}")
            return None

    @staticmethod
    async def get_saved_queries_for_notebook(
        session: AsyncSession,
        notebook_id: str,
    ) -> list[tuple[str, str]]:
        """Get all saved queries for a specific notebook. Returns list of (id, name) tuples."""
        try:
            # First verify notebook exists
            notebook_repo = NotebookRepository(session)
            notebook = await notebook_repo.get(notebook_id)
            if notebook is None:
                raise ValueError(f"Notebook with ID {notebook_id} not found")

            # Get queries for this notebook
            query_repo = QueryRepository(session)
            queries = await query_repo.get_by_notebook_id(notebook_id)
            return queries
        except ValueError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to get saved queries for notebook: {str(e)}",
                posthog_context={
                    "function": "NotebookService.get_saved_queries_for_notebook",
                    "notebook_id": notebook_id,
                },
            )
            raise

    @staticmethod
    async def get_notebook_html_version(session: AsyncSession, notebook_id: str, version_num: int) -> str | None:
        """Get specific version HTML content for a notebook."""
        try:
            dashboard_repo = DashboardRepository(session)
            dashboard = await dashboard_repo.get_version(notebook_id, version_num)
            if dashboard:
                return dashboard.html_content
            return None
        except Exception as e:
            logger.error(f"Failed to read HTML version {version_num} for notebook {notebook_id}: {str(e)}")
            return None

    @staticmethod
    async def list_dashboard_versions(session: AsyncSession, notebook_id: str) -> list[dict]:
        """Get all dashboard versions metadata for a notebook."""
        try:
            dashboard_repo = DashboardRepository(session)
            dashboards = await dashboard_repo.get_by_notebook_id(notebook_id)
            return [
                {
                    "version_num": d.version_num,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "id": d.id,
                }
                for d in dashboards
            ]
        except Exception as e:
            logger.error(f"Failed to list dashboard versions for notebook {notebook_id}: {str(e)}")
            return []
