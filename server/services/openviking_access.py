"""Knowledge-profile access grants and fail-closed authorization.

The UserPool subject/group values used here must come from the verified
external identity bridge on ``AuthContext``.  Local user ids are only used for
the profile creator's implicit manager access.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

ROLE_ACTIONS: dict[str, frozenset[str]] = {
    "Reader": frozenset({"list", "search", "read", "use_in_skill"}),
    "Contributor": frozenset({"list", "search", "read", "use_in_skill", "import", "reindex", "sync"}),
    "Manager": frozenset(
        {
            "list",
            "search",
            "read",
            "use_in_skill",
            "import",
            "reindex",
            "sync",
            "settings",
            "credential_rotate",
            "grant_manage",
            "delete",
        }
    ),
}


@dataclass(frozen=True)
class OpenVikingAccessGrant:
    grant_id: str
    tenant_id: str
    profile_id: str
    subject_type: str
    subject: str
    role: str
    effect: str
    actions: tuple[str, ...]
    conditions: dict[str, Any]
    reason: str
    policy_version: str
    created_at: float
    updated_at: float
    revoked_at: float | None = None

    @property
    def effective_actions(self) -> frozenset[str]:
        if self.role in ROLE_ACTIONS:
            return ROLE_ACTIONS[self.role]
        return frozenset(self.actions)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _conditions_match(
    conditions: dict[str, Any],
    *,
    context: dict[str, Any] | None,
) -> bool:
    """Evaluate only structured ABAC fields; unknown fields fail closed."""
    if not conditions:
        return True
    context = context or {}
    supported = {"environment", "client", "agent", "resource_tags", "risk", "time_window"}
    if set(conditions) - supported:
        return False
    for key in ("environment", "client", "agent", "risk"):
        expected = conditions.get(key)
        if expected is None:
            continue
        actual = context.get(key)
        values = expected if isinstance(expected, list) else [expected]
        if actual not in values:
            return False
    tags = conditions.get("resource_tags")
    if tags is not None:
        actual_tags = context.get("resource_tags") or {}
        if not isinstance(tags, dict) or not isinstance(actual_tags, dict):
            return False
        if any(actual_tags.get(key) != value for key, value in tags.items()):
            return False
    window = conditions.get("time_window")
    if window is not None:
        if not isinstance(window, dict) or not all(key in window for key in ("start", "end")):
            return False
        now = float(context.get("now", time.time()))
        if not float(window["start"]) <= now <= float(window["end"]):
            return False
    return True


def verified_subjects(auth: Any) -> tuple[str | None, tuple[str, ...]]:
    subject = getattr(auth, "external_subject", None)
    groups = getattr(auth, "external_groups", ()) or ()
    if not isinstance(subject, str) or not subject:
        subject = None
    groups = tuple(item for item in groups if isinstance(item, str) and item)
    return subject, groups


class OpenVikingAccessRepository:
    """Storage adapter deliberately accepts the profile repository's DB handle."""

    def __init__(self, db: Any, postgres: bool = False, cursor_factory: Any = None) -> None:
        self.db = db
        self.postgres = postgres
        self.cursor_factory = cursor_factory

    def ensure_tables(self) -> None:
        if self.postgres:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS openviking_access_grants (
                      grant_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                      profile_id TEXT NOT NULL, subject_type TEXT NOT NULL,
                      subject TEXT NOT NULL, role TEXT NOT NULL, effect TEXT NOT NULL,
                      actions TEXT NOT NULL, conditions TEXT NOT NULL, reason TEXT NOT NULL,
                      policy_version TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL,
                      updated_at DOUBLE PRECISION NOT NULL, revoked_at DOUBLE PRECISION
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS openviking_access_audit (
                      audit_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                      profile_id TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
                      decision TEXT NOT NULL, subject_type TEXT, subject TEXT,
                      details TEXT NOT NULL, observed_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            self.db.commit()
            return
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS openviking_access_grants (
              grant_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
              profile_id TEXT NOT NULL, subject_type TEXT NOT NULL,
              subject TEXT NOT NULL, role TEXT NOT NULL, effect TEXT NOT NULL,
              actions TEXT NOT NULL, conditions TEXT NOT NULL, reason TEXT NOT NULL,
              policy_version TEXT NOT NULL, created_at REAL NOT NULL,
              updated_at REAL NOT NULL, revoked_at REAL
            );
            CREATE INDEX IF NOT EXISTS openviking_access_scope
              ON openviking_access_grants(tenant_id, profile_id, revoked_at);
            CREATE TABLE IF NOT EXISTS openviking_access_audit (
              audit_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
              profile_id TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
              decision TEXT NOT NULL, subject_type TEXT, subject TEXT,
              details TEXT NOT NULL, observed_at REAL NOT NULL
            );
            """
        )
        self.db.commit()

    def put(self, grant: OpenVikingAccessGrant) -> OpenVikingAccessGrant:
        self.ensure_tables()
        values = (
            grant.grant_id,
            grant.tenant_id,
            grant.profile_id,
            grant.subject_type,
            grant.subject,
            grant.role,
            grant.effect,
            _json(list(grant.actions)),
            _json(grant.conditions),
            grant.reason,
            grant.policy_version,
            grant.created_at,
            grant.updated_at,
            grant.revoked_at,
        )
        if self.postgres:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO openviking_access_grants
                    (grant_id,tenant_id,profile_id,subject_type,subject,role,effect,actions,
                     conditions,reason,policy_version,created_at,updated_at,revoked_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(grant_id) DO UPDATE SET role=EXCLUDED.role,effect=EXCLUDED.effect,
                    actions=EXCLUDED.actions,conditions=EXCLUDED.conditions,reason=EXCLUDED.reason,
                    policy_version=EXCLUDED.policy_version,updated_at=EXCLUDED.updated_at,
                    revoked_at=EXCLUDED.revoked_at""",
                    values,
                )
            self.db.commit()
            return grant
        self.db.execute(
            """INSERT INTO openviking_access_grants VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(grant_id) DO UPDATE SET role=excluded.role,effect=excluded.effect,
            actions=excluded.actions,conditions=excluded.conditions,reason=excluded.reason,
            policy_version=excluded.policy_version,updated_at=excluded.updated_at,
            revoked_at=excluded.revoked_at""",
            values,
        )
        self.db.commit()
        return grant

    def _row(self, row: Any) -> OpenVikingAccessGrant:
        value = dict(row)
        return OpenVikingAccessGrant(
            grant_id=str(value["grant_id"]),
            tenant_id=str(value["tenant_id"]),
            profile_id=str(value["profile_id"]),
            subject_type=str(value["subject_type"]),
            subject=str(value["subject"]),
            role=str(value["role"]),
            effect=str(value["effect"]),
            actions=tuple(json.loads(value["actions"])),
            conditions=json.loads(value["conditions"]),
            reason=str(value["reason"]),
            policy_version=str(value["policy_version"]),
            created_at=float(value["created_at"]),
            updated_at=float(value["updated_at"]),
            revoked_at=value["revoked_at"],
        )

    def list(
        self, tenant_id: str, profile_id: str | None = None, include_revoked: bool = False
    ) -> list[OpenVikingAccessGrant]:
        self.ensure_tables()
        predicate = "" if include_revoked else " AND revoked_at IS NULL"
        profile_predicate = "" if profile_id is None else " AND profile_id = " + ("%s" if self.postgres else "?")
        params = (tenant_id,) if profile_id is None else (tenant_id, profile_id)
        if self.postgres:
            with self.db.cursor(cursor_factory=self.cursor_factory) as cursor:
                cursor.execute(
                    "SELECT * FROM openviking_access_grants WHERE tenant_id=%s"
                    + profile_predicate
                    + predicate
                    + " ORDER BY created_at",
                    params,
                )
                return [self._row(item) for item in cursor.fetchall()]
        rows = self.db.execute(
            "SELECT * FROM openviking_access_grants WHERE tenant_id=?"
            + profile_predicate
            + predicate
            + " ORDER BY created_at",
            params,
        ).fetchall()
        return [self._row(item) for item in rows]

    def revoke(self, tenant_id: str, profile_id: str, grant_id: str) -> bool:
        self.ensure_tables()
        now = time.time()
        if self.postgres:
            with self.db.cursor() as cursor:
                cursor.execute(
                    "UPDATE openviking_access_grants SET revoked_at=%s,updated_at=%s "
                    "WHERE grant_id=%s AND tenant_id=%s AND profile_id=%s AND revoked_at IS NULL",
                    (now, now, grant_id, tenant_id, profile_id),
                )
                changed = cursor.rowcount > 0
            self.db.commit()
            return changed
        result = self.db.execute(
            "UPDATE openviking_access_grants SET revoked_at=?,updated_at=? "
            "WHERE grant_id=? AND tenant_id=? AND profile_id=? AND revoked_at IS NULL",
            (now, now, grant_id, tenant_id, profile_id),
        )
        self.db.commit()
        return result.rowcount > 0

    def audit(
        self,
        tenant_id: str,
        profile_id: str,
        actor: str,
        action: str,
        decision: str,
        subject_type: str | None,
        subject: str | None,
        details: dict[str, Any],
    ) -> None:
        self.ensure_tables()
        row = (
            str(uuid.uuid4()),
            tenant_id,
            profile_id,
            actor,
            action,
            decision,
            subject_type,
            subject,
            _json(details),
            time.time(),
        )
        if self.postgres:
            with self.db.cursor() as cursor:
                cursor.execute("INSERT INTO openviking_access_audit VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", row)
            self.db.commit()
        else:
            self.db.execute("INSERT INTO openviking_access_audit VALUES(?,?,?,?,?,?,?,?,?,?)", row)
            self.db.commit()

    def audits(self, tenant_id: str, profile_id: str) -> list[dict[str, Any]]:
        self.ensure_tables()
        if self.postgres:
            with self.db.cursor(cursor_factory=self.cursor_factory) as cursor:
                cursor.execute(
                    "SELECT * FROM openviking_access_audit WHERE tenant_id=%s AND profile_id=%s ORDER BY observed_at DESC",
                    (tenant_id, profile_id),
                )
                rows = cursor.fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM openviking_access_audit WHERE tenant_id=? AND profile_id=? ORDER BY observed_at DESC",
                (tenant_id, profile_id),
            ).fetchall()
        return [dict(item) for item in rows]


def authorize(
    repository: OpenVikingAccessRepository,
    *,
    profile: Any,
    auth: Any,
    action: str,
    context: dict[str, Any] | None = None,
) -> bool:
    """Return a decision and always write a redacted allow/deny audit."""
    subject, groups = verified_subjects(auth)
    actor = subject or str(getattr(auth, "user_id", "unknown"))
    if str(profile.principal_id) == str(getattr(auth, "user_id", "")):
        repository.audit(
            str(profile.tenant_id), profile.profile_id, actor, action, "allow", "user", actor, {"source": "creator"}
        )
        return True
    grants = repository.list(str(profile.tenant_id), profile.profile_id)
    matched: list[OpenVikingAccessGrant] = []
    for grant in grants:
        if grant.subject_type == "user" and subject and grant.subject == subject:
            matched.append(grant)
        elif grant.subject_type == "group" and grant.subject in groups:
            matched.append(grant)
    applicable = [
        grant
        for grant in matched
        if action in grant.effective_actions and _conditions_match(grant.conditions, context=context)
    ]
    decision = (
        "deny"
        if any(grant.effect == "deny" for grant in applicable)
        else ("allow" if any(grant.effect == "allow" for grant in applicable) else "deny")
    )
    repository.audit(
        str(profile.tenant_id),
        profile.profile_id,
        actor,
        action,
        decision,
        "user" if subject else None,
        subject,
        {"matched_grants": len(applicable)},
    )
    return decision == "allow"


def grant_view(grant: OpenVikingAccessGrant) -> dict[str, Any]:
    return {
        "grant_id": grant.grant_id,
        "profile_id": grant.profile_id,
        "subject_type": grant.subject_type,
        "subject": grant.subject,
        "role": grant.role,
        "effect": grant.effect,
        "actions": sorted(grant.effective_actions),
        "conditions": grant.conditions,
        "reason": grant.reason,
        "policy_version": grant.policy_version,
        "created_at": grant.created_at,
        "updated_at": grant.updated_at,
        "revoked_at": grant.revoked_at,
    }
