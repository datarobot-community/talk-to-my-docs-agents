# Local Tracing Setup

## Background

Talk to My Docs uses OpenTelemetry (OTel) to track exactly what happens under the hood, from HTTP requests to CrewAI steps, LLM call durations, and token counts. When deployed on DataRobot, traces flow automatically into DataRobot's observability platform. During local development, you point your telemetry at a lightweight tracing entity and see the same traces in the same UI.

> [!IMPORTANT]
> Tracing is entirely optional. If no backend is configured, the app silently ignores telemetry and runs normally.

---

## How It Works

When you run `task agent_retrieval_agent:dev` and `task web:dev`, the app exports telemetry to `OTEL_EXPORTER_OTLP_ENDPOINT` (if set). Two services appear in the DataRobot tracing UI:

| Service | What it tracks |
| :--- | :--- |
| **`talk-to-my-docs-web-local`** | HTTP requests, database queries, outbound calls to the agent |
| **`talk-to-my-docs-agent-local`** | CrewAI task breakdowns, LLM call durations, token counts |

> [!TIP]
> The Taskfile reads from `.env` automatically (`dotenv: [".env"]`). Add your OTel credentials there once, no per-terminal exporting needed.

---

## Setup

### 1. Create a tracing entity (one-time)

The `create_tracing_shell.sh` script creates a minimal stopped custom application in DataRobot. Its only purpose is to provide a valid `entity_id` for authentication, the app is never started and consumes no compute resources. You only need to do this once per machine.

**Prerequisites:** `DATAROBOT_ENDPOINT` and `DATAROBOT_API_TOKEN` set in your environment.

```bash
./scripts/create_tracing_shell.sh
```

The script prints three variables. Copy them into your `.env` file (strip the `export` keyword and quotes):

```bash
# .env, add these lines
OTEL_EXPORTER_OTLP_ENDPOINT=https://app.datarobot.com/otel
OTEL_EXPORTER_OTLP_HEADERS=x-datarobot-entity-id=custom_application-<id>,x-datarobot-api-key=<token>
OTEL_SERVICE_NAME=custom_application-<id>
```

### 2. Start local dev as usual

```bash
task agent_retrieval_agent:dev   # terminal 1
task web:dev                     # terminal 2
```

### 3. View your traces

Open the URL printed by the script (e.g. `https://app.datarobot.com/apps/applications/<id>`) and navigate to the **Tracing** tab. Ask a question in the Talk to My Docs UI, then refresh the page, traces arrive within a few seconds.

---

## Using credentials from a deployed app

If the app is already deployed to DataRobot, you can reuse its credentials instead of creating a separate tracing entity. Find the application ID on the [Applications tab](https://app.datarobot.com/apps/applications) and an API key under [Developer Tools → API Keys](https://app.datarobot.com/account/developer-tools).

```bash
# .env, add these lines
OTEL_EXPORTER_OTLP_ENDPOINT=https://app.datarobot.com/otel
OTEL_EXPORTER_OTLP_HEADERS=x-datarobot-entity-id=custom_application-<id>,x-datarobot-api-key=<key>
OTEL_SERVICE_NAME=custom_application-<id>
```

> [!NOTE]
> Local traces will appear mixed with the deployed app's traces because they share the same `entity_id`. Use the dedicated tracing entity from [Setup](#setup) to keep them separate.

For a different region (e.g. `app.jp.datarobot.com`), substitute the endpoint URL accordingly.

---

## Scoped OTEL key (optional)

The script uses your personal API token in the `x-datarobot-api-key` header. For a narrower-scoped key, find `OTEL Key <app-id>` under **Developer Tools → API Keys** (filter by `OTEL Key`) and substitute it for your personal token.

---

## Disabling tracing

To disable all telemetry (including startup warnings), add this to your `.env`:

```bash
OTEL_SDK_DISABLED=true
```

Or simply don't set `OTEL_EXPORTER_OTLP_ENDPOINT`, the app detects this and skips telemetry automatically.

---

## Troubleshooting

**I don't see any traces.**
- Check that `.env` contains all three OTEL variables.
- Traces are sent in batches, wait ~5 seconds after your request finishes, then refresh.

**The app logs an error about missing `OTEL_EXPORTER_OTLP_HEADERS`.**
- `OTEL_EXPORTER_OTLP_ENDPOINT` is set but `OTEL_EXPORTER_OTLP_HEADERS` is missing. Without auth headers, every request is rejected. Either add `OTEL_EXPORTER_OTLP_HEADERS` to `.env`, or remove `OTEL_EXPORTER_OTLP_ENDPOINT` to disable tracing entirely.

**`create_tracing_shell.sh` fails with "DATAROBOT_ENDPOINT must be set".**
- Export both `DATAROBOT_ENDPOINT` and `DATAROBOT_API_TOKEN` before running the script, or add them to `.env` and source it first.

**`create_tracing_shell.sh` fails mid-way.**
- The script cleans up automatically on failure, any partially created resources are deleted. Re-run once the issue is resolved.
