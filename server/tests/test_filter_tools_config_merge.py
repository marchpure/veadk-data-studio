import json
from datetime import UTC, datetime

from server.tools.filters import (
    _apply_updates_to_filters_by_id,
    _normalize_filter_definition_payload,
    _normalize_options,
    _timeout_fallback_filter_options_response,
    _upsert_filters_by_identity,
)


def test_upsert_filters_by_identity_updates_existing_and_keeps_stable_id() -> None:
    existing_filters = [
        {
            "id": "filter_created_at",
            "query_id": "q1",
            "field_name": "created_at",
            "display_label": "Created Date",
            "filter_type": "date_range",
            "operator": "between",
        }
    ]
    incoming_filters = [
        {
            "id": "new_id_should_not_replace",
            "query_id": "q1",
            "field_name": "created_at",
            "display_label": "Tenant Created Date",
            "filter_type": "date_range",
            "operator": "between",
        }
    ]

    merged, created_count, updated_count = _upsert_filters_by_identity(existing_filters, incoming_filters)

    assert created_count == 0
    assert updated_count == 1
    assert len(merged) == 1
    assert merged[0]["id"] == "filter_created_at"
    assert merged[0]["display_label"] == "Tenant Created Date"


def test_upsert_filters_by_identity_deduplicates_existing_and_adds_new() -> None:
    existing_filters = [
        {
            "id": "filter_created_at",
            "query_id": "q1",
            "field_name": "created_at",
            "display_label": "Created Date",
            "filter_type": "date_range",
            "operator": "between",
        },
        {
            "id": "duplicate_should_be_ignored",
            "query_id": "q1",
            "field_name": "created_at",
            "display_label": "Duplicate",
            "filter_type": "date_range",
            "operator": "between",
        },
    ]
    incoming_filters = [
        {
            "query_id": "q2",
            "field_name": "status",
            "display_label": "Status",
            "filter_type": "select",
            "operator": "eq",
            "options": ["active", "inactive"],
        }
    ]

    merged, created_count, updated_count = _upsert_filters_by_identity(existing_filters, incoming_filters)

    assert created_count == 1
    assert updated_count == 0
    assert len(merged) == 2
    assert merged[0]["id"] == "filter_created_at"
    assert merged[1]["query_id"] == "q2"
    assert merged[1]["field_name"] == "status"
    assert merged[1]["id"].startswith("filter_")


def test_apply_updates_to_filters_by_id_updates_all_matching_entries() -> None:
    filters = [
        {
            "id": "filter_t_name",
            "query_id": "q1",
            "field_name": "t.name",
            "filter_type": "text",
            "operator": "contains",
        },
        {
            "id": "filter_t_name",
            "query_id": "q2",
            "field_name": "t.name",
            "filter_type": "text",
            "operator": "contains",
        },
        {
            "id": "filter_c_status",
            "query_id": "q1",
            "field_name": "c.status",
            "filter_type": "select",
            "operator": "eq",
        },
    ]

    updated_filters, updated_count = _apply_updates_to_filters_by_id(
        filters,
        "filter_t_name",
        {"filter_type": "select", "operator": "eq"},
    )

    assert updated_count == 2
    assert updated_filters[0]["filter_type"] == "select"
    assert updated_filters[1]["filter_type"] == "select"
    assert updated_filters[2]["filter_type"] == "select"
    assert updated_filters[2]["id"] == "filter_c_status"


def test_normalize_options_converts_non_json_types_and_deduplicates() -> None:
    raw_values = [
        "A",
        "A",
        datetime(2026, 2, 9, 10, 30, tzinfo=UTC),
        None,
        b"bytes",
    ]
    options, null_count = _normalize_options(raw_values, limit=10)

    assert options[0] == "A"
    assert options[1] == "2026-02-09T10:30:00+00:00"
    assert options[2] == "bytes"
    assert null_count == 1


def test_timeout_fallback_filter_options_response_is_successful_text_fallback() -> None:
    payload = json.loads(
        _timeout_fallback_filter_options_response(
            column_name="category",
            table_name="orders",
            timeout_seconds=12,
        )
    )
    assert payload["success"] is True
    assert payload["timed_out"] is True
    assert payload["recommended_filter_type"] == "text"
    assert payload["recommended_operator"] == "contains"


def test_normalize_filter_definition_payload_downgrades_empty_select() -> None:
    payload = _normalize_filter_definition_payload(
        {
            "query_id": "q1",
            "field_name": "tenant_name",
            "display_label": "Tenant Name",
            "filter_type": "select",
            "operator": "eq",
            "options": ["", "   ", None],
        }
    )

    assert payload["filter_type"] == "text"
    assert payload["operator"] == "contains"
    assert payload["options"] is None
