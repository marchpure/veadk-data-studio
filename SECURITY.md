# Security Policy

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues.

Report suspected vulnerabilities by emailing security@byaan.ai. Include:

- Affected version or commit SHA.
- Deployment mode: desktop, community Docker, self-hosted, or hosted.
- Steps to reproduce.
- Impact and affected components.
- Any proof-of-concept details that are safe to share.

We aim to acknowledge reports within 3 business days and provide a remediation plan or status update within 10 business days.

## Scope

Security-sensitive areas include:

- Database connector execution paths.
- Read-only validation and query guardrails.
- MCP authentication and tool execution.
- Credential storage and encryption.
- File upload and local file access.
- Authentication, invitations, RBAC, and organization boundaries.
- Hosted/team deployment configuration.

## Supported Versions

Security fixes target the latest released version and the current `main` branch unless otherwise announced.

## Operational Guidance

Use database credentials with the least privilege required for analysis. For production systems, use read-only database users even though Byaan includes application-level read-only guardrails.

Review [docs/security/read-only-guardrails.md](docs/security/read-only-guardrails.md) before connecting sensitive production data.
