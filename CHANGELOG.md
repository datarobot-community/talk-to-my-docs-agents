# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


## [11.7.3] - 2026-05-11

### Added

- Improved OTEL coverage: LiteLLM calls are now traced and trace context is propagated to downstream LLM requests.

### Changed

- Updated retrieval agent default model to `anthropic/claude-sonnet-4-5-20250929`.
- Renamed sample documents folder from `sample_documents/` to `static_docs/`.


## [11.7.2] - 2026-04-30

### Added

- Simplified local tracing setup with a new `scripts/create_tracing_shell.sh` helper script.

### Changed

- Switched retrieval agent to hierarchical crew process with a dedicated Manager Agent to significantly speed up the app.
- Updated OTEL span attribute names to align with GenAI semantic conventions.

### Fixed

- Fixed span aggregation for chat completions.

### Security

- Bumped dependencies to address security vulnerabilities.


## [11.7.1] - 2026-04-20

### Security

- Bumped `axios` to 1.15.1 to address denial-of-service, SSRF via NO_PROXY hostname bypass, and cloud metadata exfiltration advisories.


## [11.7.0] - 2026-04-17

## Added

- Added local tracing setup guide.
- Added OpenTelemetry tracing attributes.
- Added user display preferences for theme and language.
- Added tooltip and copy button for chat error messages.

## Changed

- Improved chat error message UX and tooltip behavior.
- Excluded kube-probe and /health requests from tracing noise.
- Updated AF Component Agent.
- Applied localization updates.
- Restructured Settings: App Settings now combines Display and Data connections.
- Synced component templates from upstream:
 - af-component-datarobot-recipe
 - af-component-agent
 - af-component-base
 - af-component-react
 - af-component-fastapi-backend
 - af-component-llm


## [11.5.2] - 2026-02-13

### Added

- Real-time agent task progress: stream crew execution events to UI
- ESLint rules for Tailwind

### Changed

- Theme changed to match corporate DataRobot design. This includes colors, fonts, paddings, and typography. Reusable shadcn components from `@dr-ui` registry are installed.
- OAuth provider tiles: add status and an Edit button, which allows selecting another account.

### Fixed

- Fix the case when the user revoked access to an OAuth provider.
- Crew initialization.

## [11.5.0] - 2026-01-21

### Added

- Added a new LLM configuration `infra/configurations/llm/gateway_direct.py` which skips creating an LLM model. (Faster initial deployment, but doesn't support the features - RAG, guardrails, tracing - of a deployed model.)
- Filled out DataRobot playgrounds for agent and LLM custom models when deployed.
- Better UX to indicate which component is not ready to serve the request (Agent vs LLM Blueprint vs LLM Gateway).
- Updated `.env.template` to include `LLM_DEFAULT_MODEL` configuration.

### Changed

- Refactored `agent_retrieval_agent` to leverage [`datarobot_genai`](https://github.com/datarobot-oss/datarobot-genai) library, removing unneeded code.
- Removed execution environment build (`agent_retrieval_agent/docker_context`) in favor of default agent execution environment, saving significant deployment time. This can be regenerated with `task agent:build-docker-image` for those needing to customize execution environments.
- Increased maximum completion tokens limit for better response quality.
- Refined expected output format for document summary.
- CLI improvements for LLM default selection.
- Updated component templates (fastapi-backend, llm, base, react) to latest versions.

### Fixed

- Fixed chat alignment in Firefox.
- Fixed suggestions from the Agent.
- Fixed issue with empty knowledge base response.
- Updated dependencies to resolve security vulnerabilities.

### Documentation

- Comprehensive README updates with improved Quick Start section.
- Updated macOS installation instructions to include dr-cli.
- Improved usage instructions for `LLM_DEFAULT_MODEL`.

## [0.2.9] - 2025-12-04

- Bump litellm version to 1.79.3 with retry-after header support for errors 502, 503, 504

### Fixed

- Fixed an issue where the LLM Gateway dependency was incorrectly required for all LLM configurations.

## [0.2.8] - 2025-11-25

### Changed

- Switched Pulumi frontend build to `npm ci` for reproducible installs and deterministic caching
- Added sha-based triggers that watch key source, asset, and config files (including `public/`, Vite/tailwind configs, `.npmrc`, and tsconfig variants) so rebuilds only run when inputs change

### Documentation

- Updated usage instructions for LLM_DEFAULT_MODEL
- Updated README Quick Start section

## [0.2.7] - 2025-11-19

### Documentation

- Refreshed setup guide and README links to reflect the latest CLI workflow

## [0.2.6] - 2025-11-17

### Fixed

- Hardened application startup scripts to better support pre-bundled images

## [0.2.5] - 2025-11-12

### Fixed

- Corrected issue with uniqueness in OAuth provider identities
- Fixed issue with overriding SQLite file during write operation

## [0.2.2] - 2025-10-21

### Fixed

- Corrected issue with uniqueness in OAuth provider identities

## [0.2.1] - 2025-10-21

### Added

- Improved table paddings
- Display file preview size relative to actual size
- Added file upload indication
- Added additional session invalidation logic
- Implemented suggested prompts when KB/files are selected
- Added validation messages to KB/chat actions
- Switched message retrieval to SSE (server-sent events) instead of polling
- Updated app navigation to highlight the active page correctly
- Visual updates for links and knowledge bases
- Upgraded DataRobot integration to use Core

### Fixed

- Fixed markdown response rendering for 4o mini and added animation
- Disabled “Create KB” button when required fields are missing
- Fixed fast refresh issues and updated exports
- Fixed button text alignment and consistency
- Fixed table paddings

## [0.2.0] - 2025-09-25

### Added

- Initial release of Talk to My Docs.
- Storing uploaded files in persistent storage. Files will not be lost between container restarts.
- User sees only own chats.
- Added support of DB migrations with [Alembic](https://alembic.sqlalchemy.org/en/latest/).
