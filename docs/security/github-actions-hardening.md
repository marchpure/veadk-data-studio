# GitHub Actions Hardening

This repository treats pull requests from forks as untrusted code. PR checks must prove that the change builds and tests cleanly without giving that code access to credentials, publish tokens, signing keys, cloud storage, or privileged GitHub tokens.

## PR Workflow Rules

- Use `pull_request` for CI on contributor code.
- Do not use `pull_request_target` for jobs that check out, build, install, test, or otherwise execute PR code.
- Set workflow or job permissions explicitly. PR jobs should use `contents: read` unless a narrower documented exception is required.
- Do not pass repository, organization, cloud, package registry, Apple signing, Docker, Infisical, or R2 secrets to PR jobs.
- Use `actions/checkout` with `persist-credentials: false` so the token is not written into the local Git config.
- Keep PR caches separate from release/deploy caches. Do not reuse cache scopes between untrusted PR jobs and privileged publish jobs.
- Treat PR titles, branch names, bodies, labels, issue comments, and commit messages as attacker-controlled input. Do not interpolate them directly into shell scripts.

## Privileged Workflow Rules

Privileged workflows are allowed to fetch secrets, sign binaries, publish Docker images, write release artifacts, or upload to R2 only when they run from trusted repository events:

- `workflow_dispatch` by a maintainer
- protected `release` or tag events
- protected branch pushes after review

Privileged workflows should:

- declare least-privilege `permissions`
- use GitHub Environments for production/staging approval gates
- avoid checking out or executing fork PR code
- validate the source ref before loading secrets; production release and Docker dispatches must run from `main`, and release tags must point to commits contained in `origin/main`
- restrict production release, deploy, Docker promotion, R2 test, and self-hosted publish workflows to the owner account before loading secrets
- use non-canceling `concurrency` for publishing jobs
- pass secrets only to the step that needs them
- avoid printing secret-derived values or generated config containing secrets
- do not ship OAuth client secrets in desktop or browser artifacts; use PKCE, user-supplied self-hosted settings, or a server-side exchange instead

## Required Repository Settings

Configure these in GitHub after merging the workflow files:

- Require `Pull Request CI`, `Dependency Review`, and `Workflow Security` before merging to `main`.
- Require review from CODEOWNERS for `.github/**`, lockfiles, Docker files, package manifests, and release config.
- Require approval before running workflows from first-time contributors.
- Restrict who can run `workflow_dispatch` release, deploy, Docker, R2, and promotion workflows.
- Protect `main`, require CODEOWNER approval, and require the CI/security checks above before merge. Workflow hardening prevents direct PR secret exposure, but a malicious change that is reviewed and merged can still run later in release/deploy jobs.
- Enable secret scanning and push protection.
- Enable Dependabot alerts and dependency graph.
- Enable CodeQL after the repository is public or GitHub Code Security is available. Private repositories without Code Security cannot upload CodeQL code-scanning results.
- Configure `production` and `staging` environments with required reviewers before exposing deployment or signing secrets there. Empty environments are enough to start jobs, but they do not provide a review gate or scoped secrets.

## Incident Class Covered

The TanStack supply-chain incident combined a privileged PR workflow pattern with cache poisoning and token exposure. The guardrail here is privilege separation: untrusted PR code can run checks, but it cannot access secrets, write tokens, privileged caches, or publish paths.

References:

- GitHub secure use reference: https://docs.github.com/en/actions/reference/security/secure-use
- GitHub script injection guidance: https://docs.github.com/en/actions/concepts/security/script-injections
- TanStack postmortem: https://tanstack.com/blog/npm-supply-chain-compromise-postmortem
