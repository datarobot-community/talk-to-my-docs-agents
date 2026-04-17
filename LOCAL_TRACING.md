# Local Tracing Setup

## Background

Talk to My Docs uses OpenTelemetry (OTel) to track exactly what is happening under the hood, from standard web requests all the way to complex LLM logic. 

**When deployed on DataRobot**, these traces automatically flow into DataRobot's internal observability platform. You don't need to configure anything, as the platform manages the necessary secrets during deployment.

**During local development**, however, that internal DataRobot collector isn't reachable by default. This guide explains how to spin up a local tracing tool so you can see those same traces right on your machine. 

> [!IMPORTANT]
> If you don't care about tracing right now, you don't need to do anything. If a tracing backend isn't running, the app simply ignores the telemetry data and continues running normally without crashing.

---

## Quick Start

If you just want to see traces quickly without installing heavy infrastructure, Jaeger is your best bet. 

```bash
# 1. Start a Jaeger collector (single container, zero setup)
docker run -d --name jaeger \
  -p 4317:4317 -p 4318:4318 -p 16686:16686 \
  jaegertracing/jaeger:latest

# 2. Start the app as usual
task agent_retrieval_agent:dev   # terminal 1
task web:dev                     # terminal 2

# 3. View your traces
# Open http://localhost:16686 in your browser and pick a service from the dropdown.
```

For a richer experience (like metrics, service maps, and logs), you can use SigNoz, check out [Option 2](#option-2-signoz) below. If you want to skip local infrastructure entirely, see [Option 1](#option-1-datarobot-no-local-infra-required).

---

## How Tracing Works in This Project

When you run `task web:dev` and `task agent_retrieval_agent:dev`, the application automatically points telemetry data to `http://localhost:4318`. 

Here is what gets tracked:

| Service | Local Service Name | What it Tracks |
| :--- | :--- | :--- |
| **Web App** | `talk-to-my-docs-web-local` | HTTP requests, database queries, and custom web events. |
| **Agent** | `talk-to-my-docs-agent-local` | CrewAI tasks, individual agent steps, LLM call durations, and token counts. |

> [!TIP]
> If you are running your tracing tool on a different port, you can override `OTEL_EXPORTER_OTLP_ENDPOINT` in your terminal before running the startup tasks.

---

## Choosing a Tracing Tool

Not sure which setup to use? Here is a quick comparison:

| Feature | DataRobot | SigNoz | Jaeger |
| :--- | :--- | :--- | :--- |
| **Setup required** | None (needs a deployed app) | Clone repo + `docker compose` | Single `docker run` command |
| **UI capabilities** | DataRobot tracing tab | **Rich:** traces, metrics, service maps | **Basic:** trace search only |
| **Local memory usage**| Zero | ~2 GB RAM (runs ClickHouse) | Minimal |
| **Data persistence** | Saved by DataRobot | Survives container restarts | Lost when container stops |
| **Isolation** | Mixed with deployed app traces | Fully isolated to your machine | Fully isolated to your machine |
| **Best for...** | Verifying how traces will look in production | Deep-dive debugging and regular dev | Quick, one-off investigations |

---

## Option 1: DataRobot (No local infra required)

If the app is already deployed to DataRobot, you can route your local traces directly to DataRobot's telemetry backend. This means you don't have to run Docker locally, and you can view your local traces in the exact same UI as production. 

**What you need:** The `APPLICATION_ID` and OTel credentials from a currently deployed custom application.

### 1. Get the Credentials
You can grab all you need from DataRobot's UI. API key can be found on [API keys and tools](https://app.datarobot.com/account/developer-tools) page, and check your application ID on the [Applications tab](https://app.datarobot.com/apps/applications).

```text
OTEL_EXPORTER_OTLP_ENDPOINT = [https://app.datarobot.com/otel](https://app.datarobot.com/otel)
OTEL_EXPORTER_OTLP_HEADERS  = x-datarobot-entity-id=custom_application-<id>,x-datarobot-api-key=<key>
OTEL_SERVICE_NAME           = custom_application-<app-id>
```
> [!NOTE]
> The `x-datarobot-api-key` can be the dedicated OTel scoped API key shown in [API keys and tools](https://app.datarobot.com/account/developer-tools) created along with your app, or your own personal DataRobot API token.

### 2. Start the App
Export those variables in your terminal, then run the local dev servers:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=[https://app.datarobot.com/otel](https://app.datarobot.com/otel)
export OTEL_EXPORTER_OTLP_HEADERS="x-datarobot-entity-id=custom_application-<id>,x-datarobot-api-key=<key>"
export OTEL_SERVICE_NAME=custom_application-<id>

task agent_retrieval_agent:dev   # terminal 1
task web:dev                     # terminal 2
```

Your traces will now appear in the DataRobot UI under **Deployments → \<your app\> → Tracing**.

**Caveats:**
* Local traces will be mixed in with the deployed app's traces because they share the same service name.
* For a different region (e.g., `app.jp.datarobot.com`), substitute the endpoint URL accordingly.

---

## Option 2: SigNoz

SigNoz is a powerful, open-source observability platform. It requires a bit more RAM but gives you a production-grade UI locally.

### 1. Install
Clone the SigNoz repository to your machine:
```bash
git clone -b main [https://github.com/SigNoz/signoz.git](https://github.com/SigNoz/signoz.git) <repositories-home>/signoz
```

### 2. Fix the Port Conflict
SigNoz defaults to port **8080**, which conflicts with our local web app. 
Open `deploy/docker/docker-compose.yaml` inside the cloned SigNoz repo and change the port mapping for the UI:

```yaml
ports:
  - "8081:8080"  # Change the left side from 8080 to 8081
```

### 3. Start SigNoz
> [!IMPORTANT]
> You must navigate into the `deploy/docker/` directory before running the compose command, or it will fail.

```bash
cd <repositories-home>/signoz/deploy/docker
docker compose up -d --remove-orphans
```

Open the UI at [http://localhost:8081](http://localhost:8081). 

### 4. Stop SigNoz
```bash
cd <repositories-home>/signoz/deploy/docker
docker compose down
```

---

## Option 3: Jaeger

Jaeger is lightweight and runs in a single container. It's perfect if you just need to check a trace quickly and don't care about saving the data.

### 1. Start Jaeger
```bash
docker run -d --name jaeger \
  -p 4317:4317 \
  -p 4318:4318 \
  -p 16686:16686 \
  jaegertracing/jaeger:latest
```

Open the UI at [http://localhost:16686](http://localhost:16686). Select a service from the dropdown to start exploring.

### 2. Stop Jaeger
```bash
docker rm -f jaeger
```

---

## What You Will See

After you ask a question in the Talk to My Docs UI, look for these services in your tracing tool:

* **`talk-to-my-docs-web-local`**: Look here for API response times, database queries, and the outbound network calls made to the agent.
* **`talk-to-my-docs-agent-local`**: Look here for the Data Science heavy-lifting. You will see CrewAI step breakdowns, LLM call durations, and token counts for your prompts.

> [!NOTE]
> Traces are sent in batches, so they usually appear in the UI a few seconds after your request finishes.

---

## Troubleshooting

**I don't see any traces in the UI.**
* Check if the Docker container is actually running: `docker ps`
* Verify the environment variable in your terminal: run `echo $OTEL_EXPORTER_OTLP_ENDPOINT` (it should output `http://localhost:4318`).
* Be patient! The app batches telemetry data. Wait ~5 seconds and refresh the page.

**SigNoz containers keep crashing.**
* Docker Desktop needs at least **4 GB of RAM** to run SigNoz. Check your Docker Desktop settings (Settings → Resources).

**I changed the SigNoz port to 8081, but the UI won't load.**
* If you ran `docker compose up` *before* editing the YAML file, the old port is still bound. Run `docker compose down`, ensure the file is saved, and run `docker compose up -d` again.

---

## Silencing Telemetry Errors

If you aren't running a backend, the app suppresses connection errors automatically so they don't spam your terminal. You'll see one warning on the first failed export, and then nothing else.

If you want to disable telemetry entirely (including that first warning), just run:
```bash
export OTEL_SDK_DISABLED=true
```
