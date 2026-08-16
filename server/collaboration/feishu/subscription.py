from __future__ import annotations

FEISHU_REQUIRED_EVENT_TYPES = ["im.message.receive_v1"]


def feishu_event_subscription_payload(config_json: dict | None) -> dict:
    config = config_json or {}
    existing = dict(config.get("event_subscription") or {})
    first_event_observed_at = existing.get("first_event_observed_at")
    last_event_observed_at = existing.get("last_event_observed_at")
    return {
        "mode": "websocket",
        "required_event_types": existing.get("required_event_types") or FEISHU_REQUIRED_EVENT_TYPES,
        "remote_status": existing.get("remote_status") or "manual_developer_console_check_required",
        "first_event_observed_at": first_event_observed_at,
        "last_event_observed_at": last_event_observed_at,
        "last_event_id": existing.get("last_event_id"),
        "ready": bool(last_event_observed_at),
        "operator_action": existing.get("operator_action")
        or "Enable and publish im.message.receive_v1 in the Feishu developer console for this app.",
    }
