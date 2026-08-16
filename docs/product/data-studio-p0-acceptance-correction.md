# Unified Data Studio P0 Acceptance Correction

This document records acceptance-gate corrections after the prior `8080_READY`
claim. It is intentionally evidence-first: each section names the command,
observed output, and current status.

## Known Pre-existing Failures

### Connection encryption persistence workflow

- Test: `tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow`
- Error summary: `TypeError: 'NoneType' object is not subscriptable` at `assert decrypted["password"] == "SuperSecret123!@#"`
- Current status: pre-existing known failure, not introduced by `agent/data-studio-p0`
- Owner / next step: connection credential encryption owner should investigate tenant-context/session key selection for `Connection.get_decrypted_connection_obj`. This correction session does not repair it because the fix touches credential encryption behavior rather than the Data Studio acceptance gate itself.

Base-SHA reproduction:

```bash
git worktree add --detach /Users/bytedance/worktrees/byaan-data-studio-p0-base86 86fbace663a68dff40d1a2e8713056d4599b60d8
cd /Users/bytedance/worktrees/byaan-data-studio-p0-base86/server
UV_HTTP_TIMEOUT=300 PYTHONPATH=..:tests uv run pytest tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow -q
```

Observed base-SHA output:

```text
FAILED tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow
tests/integration/test_connections_workflows.py:235: in test_connection_encryption_persistence_workflow
    assert decrypted["password"] == "SuperSecret123!@#"
           ^^^^^^^^^^^^^^^^^^^^^
E   TypeError: 'NoneType' object is not subscriptable
1 failed, 9 warnings in 0.43s
```

Current-HEAD reproduction:

```bash
cd /Users/bytedance/worktrees/byaan-data-studio-p0/server
PYTHONPATH=..:tests uv run pytest tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow -q
```

Observed current-HEAD output:

```text
FAILED tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow
tests/integration/test_connections_workflows.py:235: in test_connection_encryption_persistence_workflow
    assert decrypted["password"] == "SuperSecret123!@#"
           ^^^^^^^^^^^^^^^^^^^^^
E   TypeError: 'NoneType' object is not subscriptable
1 failed, 9 warnings in 0.48s
```

Pre-existing basis: the same assertion failure reproduces at base SHA
`86fbace663a68dff40d1a2e8713056d4599b60d8`, before the
`agent/data-studio-p0` commits.
