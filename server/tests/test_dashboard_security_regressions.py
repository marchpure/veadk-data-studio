from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from server.routers import folders
from server.schemas.query import BatchExecuteSavedQueriesRequest


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason=(
        "viewer dashboard batch currently forwards caller-supplied query IDs without proving "
        "they are bound to the requested dashboard version/notebook"
    ),
)
async def test_viewer_dashboard_batch_rejects_query_id_not_bound_to_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    dashboard_id = uuid4()
    viewer_user_id = uuid4()
    unbound_query_id = uuid4()
    executed: dict[str, list[str]] = {}

    async def fake_require_viewer_session(_dashboard_id, _viewer_session):
        assert _dashboard_id == dashboard_id
        return viewer_user_id

    async def fake_can_access_dashboard_via_folder(requested_dashboard_id, user_id, session):
        assert requested_dashboard_id == dashboard_id
        assert user_id == viewer_user_id
        assert session is not None
        return True

    async def fake_execute_batch_saved_queries(*, session, query_ids=None, queries_with_filters=None, max_parallel=5):
        assert session is not None
        assert queries_with_filters is None
        assert max_parallel == 5
        executed["query_ids"] = [str(query_id) for query_id in (query_ids or [])]
        return {
            "success": True,
            "message": "All queries executed successfully",
            "data": [],
            "partial_success": False,
            "total_queries": len(query_ids or []),
            "successful_queries": len(query_ids or []),
            "failed_queries": 0,
            "total_execution_time_ms": 0.0,
        }

    monkeypatch.setattr(folders, "_require_viewer_session", fake_require_viewer_session)
    monkeypatch.setattr(folders.FolderService, "can_access_dashboard_via_folder", fake_can_access_dashboard_via_folder)
    monkeypatch.setattr(folders.QueryService, "execute_batch_saved_queries", fake_execute_batch_saved_queries)

    with pytest.raises(HTTPException) as exc:
        await folders.execute_viewer_dashboard_queries(
            dashboard_id=dashboard_id,
            request=BatchExecuteSavedQueriesRequest(query_ids=[unbound_query_id]),
            session=object(),
            viewer_session="viewer-session",
            origin="https://app.example.test",
        )

    assert exc.value.status_code == 403
    assert "query_ids" not in executed
