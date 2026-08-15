from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from typing import Any

from server.repositories.queries import QueryRepository
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


def get_default_operator(filter_type: str) -> str:
    mapping = {
        "select": "eq",
        "multiselect": "in",
        "date_range": "between",
        "number_range": "between",
        "text": "contains",
    }
    return mapping.get((filter_type or "").lower(), "eq")


def infer_data_type(filter_type: str, options: list[Any] | None = None) -> str:
    normalized = (filter_type or "").lower()
    if normalized == "number_range":
        return "number"
    if normalized == "date_range":
        return "date"
    if normalized in {"select", "multiselect"} and options:
        sample = options[0]
        if isinstance(sample, bool):
            return "boolean"
        if isinstance(sample, (int, float)):
            return "number"
    return "string"


def allowed_ops_for_filter_type(filter_type: str) -> list[str]:
    mapping = {
        "select": ["eq", "ne", "in"],
        "multiselect": ["in"],
        "date_range": ["between", "gte", "lte", "eq"],
        "number_range": ["between", "gte", "lte", "eq", "gt", "lt"],
        "text": ["contains", "like", "eq"],
    }
    return mapping.get((filter_type or "").lower(), ["eq", "contains", "in", "between", "gte", "lte"])


def looks_like_date_string(value: str) -> bool:
    if not isinstance(value, str) or len(value) < 8:
        return False
    date_patterns = [
        r"^\d{4}-\d{2}-\d{2}",
        r"^\d{4}/\d{2}/\d{2}",
        r"^\d{2}/\d{2}/\d{4}",
        r"^\d{2}-\d{2}-\d{4}",
    ]
    return any(re.match(pattern, value.strip()) for pattern in date_patterns)


def infer_filter_type(options: list[Any], column_name: str) -> str:
    if not options:
        return "text"

    sample = options[0]
    distinct_count = len(options)

    if isinstance(sample, (datetime, date)):
        return "date_range"

    col_lower = (column_name or "").lower()
    date_keywords = ["date", "time", "created", "updated", "timestamp", "birth", "expiry"]
    if any(keyword in col_lower for keyword in date_keywords):
        return "date_range"

    if isinstance(sample, str) and looks_like_date_string(sample):
        return "date_range"

    if isinstance(sample, bool) or (
        distinct_count == 2 and {str(v).lower() for v in options} <= {"true", "false", "yes", "no", "1", "0", "t", "f"}
    ):
        return "select"

    if isinstance(sample, (int, float)):
        return "select" if distinct_count <= 10 else "number_range"

    if isinstance(sample, str):
        if distinct_count <= 15:
            return "select"
        if distinct_count <= 50:
            return "multiselect"
        return "text"

    return "select"


def normalize_filter_id(query_id: str, field_name: str) -> str:
    """
    Generate a stable filter key from source field identity.

    We intentionally avoid query_id in the generated key so that regenerated queries can
    reuse the same logical filter keys and stay in sync with existing dashboards.
    """
    _ = query_id  # kept for backward-compatible signature
    field_raw = str(field_name or "").strip()
    field_token = re.sub(r"[^a-zA-Z0-9_]", "_", field_raw.replace(".", "_")).strip("_").lower() or "field"
    filter_id = f"filter_{field_token}"
    if len(filter_id) <= 64:
        return filter_id

    digest = hashlib.sha1(field_raw.encode("utf-8")).hexdigest()[:8]
    truncated = field_token[: max(1, 64 - len("filter__") - len(digest))]
    return f"filter_{truncated}_{digest}"[:64]


def _is_generic_display_label(label: str, field_name: str) -> bool:
    normalized_label = (label or "").strip().lower()
    normalized_field = (field_name or "").strip().lower()
    return not normalized_label or normalized_label == normalized_field


def _filter_type_priority(filter_type: str) -> int:
    normalized = (filter_type or "").lower()
    # Prefer richer controls over generic text when definitions drift.
    priorities = {
        "select": 50,
        "multiselect": 45,
        "date_range": 40,
        "number_range": 35,
        "text": 30,
    }
    return priorities.get(normalized, 10)


def _option_signature(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, default=str)
    except Exception:
        encoded = str(value)
    return f"{type(value).__name__}:{encoded}"


def _merge_filter_options(filter_group: list[dict[str, Any]]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for entry in filter_group:
        options = entry.get("options")
        if not isinstance(options, list):
            continue
        for option in options:
            if option is None:
                continue
            if isinstance(option, str):
                option = option.strip()
                if not option:
                    continue
            signature = _option_signature(option)
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(option)
    return merged


def _build_canonical_filter_definition(filter_group: list[dict[str, Any]]) -> dict[str, Any]:
    if not filter_group:
        return {}

    ranked = sorted(
        filter_group,
        key=lambda entry: (
            _filter_type_priority(str(entry.get("filter_type", "text"))),
            len(entry.get("options")) if isinstance(entry.get("options"), list) else 0,
            1
            if not _is_generic_display_label(
                str(entry.get("display_label", "")),
                str(entry.get("field_name", "")),
            )
            else 0,
        ),
        reverse=True,
    )
    representative = ranked[0]
    canonical_type = str(representative.get("filter_type", "text")).lower()

    merged_options = _merge_filter_options(filter_group)
    if canonical_type in {"select", "multiselect"} and not merged_options:
        canonical_type = "text"

    allowed_operators = allowed_ops_for_filter_type(canonical_type)
    candidate_operator = str(representative.get("operator", "")).lower()
    canonical_operator = (
        candidate_operator if candidate_operator in allowed_operators else get_default_operator(canonical_type)
    )

    label_candidates = [
        str(entry.get("display_label", "")).strip()
        for entry in filter_group
        if not _is_generic_display_label(
            str(entry.get("display_label", "")),
            str(entry.get("field_name", "")),
        )
    ]
    canonical_label = (
        label_candidates[0]
        if label_candidates
        else str(representative.get("display_label") or representative.get("field_name") or "Filter")
    )

    return {
        "display_label": canonical_label,
        "filter_type": canonical_type,
        "operator": canonical_operator,
        "options": merged_options if canonical_type in {"select", "multiselect"} else None,
        "data_type": infer_data_type(canonical_type, merged_options),
    }


def harmonize_filter_definitions(raw_filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize and harmonize filter definitions.

    - Canonicalize IDs from source field identity.
    - Deduplicate repeated `(query_id, field_name)` entries.
    - Ensure filters sharing the same ID expose a consistent UI definition
      (type/operator/options/label), avoiding nondeterministic UI drift.
    """
    normalized: list[dict[str, Any]] = []
    seen_identity: set[tuple[str, str]] = set()

    for item in raw_filters:
        if not isinstance(item, dict):
            continue

        entry = dict(item)
        query_id = str(entry.get("query_id", "")).strip()
        field_name = str(entry.get("field_name", "")).strip()
        if not field_name:
            continue

        if query_id:
            identity = (query_id, field_name.lower())
            if identity in seen_identity:
                continue
            seen_identity.add(identity)

        entry["query_id"] = query_id
        entry["field_name"] = field_name
        entry["id"] = normalize_filter_id(query_id=query_id, field_name=field_name)
        normalized.append(entry)

    by_id: dict[str, list[dict[str, Any]]] = {}
    for entry in normalized:
        by_id.setdefault(str(entry.get("id", "")), []).append(entry)

    canonical_by_id = {filter_id: _build_canonical_filter_definition(group) for filter_id, group in by_id.items()}

    harmonized = [{**entry, **canonical_by_id.get(str(entry.get("id", "")), {})} for entry in normalized]
    harmonized.sort(
        key=lambda entry: (
            str(entry.get("display_label") or entry.get("field_name") or "").lower(),
            str(entry.get("id") or ""),
            str(entry.get("query_id") or ""),
        )
    )
    return harmonized


def build_filter_contract_for_query(
    query_id: str,
    query_filters: list[dict[str, Any]],
    existing_contract_json: str | None,
) -> str:
    try:
        existing = json.loads(existing_contract_json) if existing_contract_json else {}
        existing_filters = existing.get("filters", []) if isinstance(existing, dict) else []
    except json.JSONDecodeError:
        existing_filters = []

    by_id: dict[str, dict[str, Any]] = {}
    for item in existing_filters:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item["id"])] = item

    for f in query_filters:
        filter_id = str(f.get("id", "")).strip()
        if not filter_id:
            continue

        filter_type = str(f.get("filter_type", "text")).lower()
        allowed_operators = allowed_ops_for_filter_type(filter_type)
        default_operator = str(f.get("operator", allowed_operators[0] if allowed_operators else "eq")).lower()

        by_id[filter_id] = {
            "id": filter_id,
            "field_name": f.get("field_name"),
            "display_label": f.get("display_label"),
            "filter_type": filter_type,
            "data_type": infer_data_type(filter_type, f.get("options")),
            "allowed_operators": allowed_operators,
            "default_operator": default_operator,
            "options": f.get("options"),
            "query_id": query_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    contract = {
        "version": 1,
        "updated_at": datetime.now(UTC).isoformat(),
        "filters": list(by_id.values()),
    }
    return json.dumps(contract)


def merge_filters_non_destructive(
    existing_filters: list[dict[str, Any]], auto_filters: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    id_to_field: dict[str, str] = {}

    for item in existing_filters:
        if not isinstance(item, dict):
            continue
        query_id = str(item.get("query_id", "")).strip()
        field_name = str(item.get("field_name", "")).strip()
        filter_id = str(item.get("id", "")).strip()
        if query_id and field_name:
            seen_keys.add((query_id, field_name))
        if filter_id:
            seen_ids.add(filter_id)
            field_identity = field_name.lower()
            if field_identity:
                id_to_field.setdefault(filter_id, field_identity)
        merged.append(item)

    for item in auto_filters:
        if not isinstance(item, dict):
            continue
        query_id = str(item.get("query_id", "")).strip()
        field_name = str(item.get("field_name", "")).strip()
        if not query_id or not field_name:
            continue
        dedupe_key = (query_id, field_name)
        if dedupe_key in seen_keys:
            continue

        filter_copy = dict(item)
        filter_id = str(filter_copy.get("id", "")).strip() or normalize_filter_id(query_id, field_name)
        field_identity = field_name.lower()
        # Allow shared IDs across queries for the same source field (single logical UI filter).
        while filter_id in seen_ids and id_to_field.get(filter_id) not in {None, field_identity}:
            filter_id = f"{filter_id}_1"
        filter_copy["id"] = filter_id

        merged.append(filter_copy)
        seen_keys.add(dedupe_key)
        seen_ids.add(filter_id)
        if field_identity:
            id_to_field.setdefault(filter_id, field_identity)

    return merged


def normalize_filters_for_client(raw_filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize filter payload for frontend consumption.

    - Canonicalize `id` to stable field-based keys.
    - Deduplicate repeated entries by (query_id, field_name).
    - Harmonize conflicting duplicate definitions that share the same ID.
    """
    return harmonize_filter_definitions(raw_filters)


async def sync_query_filter_contracts(
    session,
    filters_list: list[dict[str, Any]],
    clear_query_ids: set[str] | None = None,
) -> list[str]:
    query_repo = QueryRepository(session)

    filters_by_query: dict[str, list[dict[str, Any]]] = {}
    for filter_obj in filters_list:
        query_id = str(filter_obj.get("query_id", "")).strip()
        if not query_id:
            continue
        filters_by_query.setdefault(query_id, []).append(filter_obj)

    updated_query_contracts: list[str] = []
    for query_id, query_filters in filters_by_query.items():
        query_obj = await query_repo.get(query_id)
        if not query_obj:
            continue
        query_obj.filter_contract = build_filter_contract_for_query(
            query_id=query_id,
            query_filters=query_filters,
            existing_contract_json=query_obj.filter_contract,
        )
        updated_query_contracts.append(query_id)

    for query_id in clear_query_ids or set():
        query_obj = await query_repo.get(query_id)
        if not query_obj:
            continue
        query_obj.filter_contract = None
        updated_query_contracts.append(query_id)

    return updated_query_contracts
