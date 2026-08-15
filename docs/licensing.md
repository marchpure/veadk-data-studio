# Licensing

Byaan uses a source-available split between the community code and teams-oriented features.

## Community Code

The community code is licensed under the [MIT License](../LICENSE).

You may use, copy, modify, distribute, sublicense, and sell copies of the MIT-licensed portions of the software, subject to the MIT license terms.

## Teams Code

The `server/ee/` directory contains Byaan for Teams features under the [Elastic License 2.0](../server/ee/LICENSE).

At a practical level, this means you may use, modify, and self-host those files under the ELv2 terms, but you may not offer the ELv2-covered software as a competing hosted or managed service.

## Feature Boundary

Community-focused code covers local and single-user workflows.

Teams-oriented features may include:

- Multi-user authentication.
- Invitations.
- RBAC.
- Organization administration.
- Google OAuth.
- Slack integration.
- Shared dashboards.
- Hosted or team deployment paths.

Check the file path and license headers before reusing code outside this repository.

## Contributions

Contributions are licensed under the license that applies to the files being modified. If a PR touches both MIT and ELv2-covered files, each change follows the license of its target file.
