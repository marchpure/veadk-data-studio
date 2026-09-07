from __future__ import annotations

import sqlite3
import uuid

from server.services.openviking_access import (
    OpenVikingAccessGrant,
    OpenVikingAccessRepository,
    authorize,
)


class _Auth:
    user_id = uuid.uuid4()
    external_subject = "user-a"
    external_groups = ("group-readers",)


class _Profile:
    tenant_id = "tenant-1"
    profile_id = "ov_profile"
    principal_id = "creator"


def _grant(effect: str, subject: str = "group-readers", role: str = "Reader") -> OpenVikingAccessGrant:
    return OpenVikingAccessGrant(
        grant_id=str(uuid.uuid4()),
        tenant_id="tenant-1",
        profile_id="ov_profile",
        subject_type="group",
        subject=subject,
        role=role,
        effect=effect,
        actions=("read",),
        conditions={},
        reason="test",
        policy_version="v1",
        created_at=1,
        updated_at=1,
    )


def test_default_deny_group_allow_and_deny_precedence() -> None:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    repo = OpenVikingAccessRepository(db)
    auth = _Auth()
    assert not authorize(repo, profile=_Profile(), auth=auth, action="read")
    repo.put(_grant("allow"))
    assert authorize(repo, profile=_Profile(), auth=auth, action="read")
    repo.put(_grant("deny"))
    assert not authorize(repo, profile=_Profile(), auth=auth, action="read")
    assert repo.audits("tenant-1", "ov_profile")


def test_creator_is_implicit_manager_and_revoke_is_immediate() -> None:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    repo = OpenVikingAccessRepository(db)
    creator = _Auth()
    creator.external_subject = None
    creator.external_groups = ()
    creator.user_id = "creator"
    assert authorize(repo, profile=_Profile(), auth=creator, action="grant_manage")
    grant = _grant("allow")
    repo.put(grant)
    assert repo.revoke("tenant-1", "ov_profile", grant.grant_id)
    assert not authorize(repo, profile=_Profile(), auth=_Auth(), action="read")
