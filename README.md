# Agent Flow Python

Agent Flow Python is a local-first AI workflow builder for creating, running, and supervising multi-agent pipelines. It combines a React/Vite control panel with a FastAPI backend, SQLite lifecycle storage, live run streaming, configurable LLM providers, safe agent file generation, and an optional IoT workflow layer for signal-driven automation.

The product is designed for two modes:

- **AI workflows** — build agent chains for analysis, implementation, QA, documentation, security review, and release assembly.
- **IoT workflows** — discover/register devices, test signal sources, map safe actions, and connect IoT-aware agents into larger pipelines.

> Agent Flow is local-first. Runtime data stays in SQLite under `app/data/agent_flow.sqlite3`. Secrets should stay in `.env` or runtime Settings and must not be committed.

## Table of Contents

- [What You Can Build](#what-you-can-build)
- [Current Capabilities](#current-capabilities)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Start, Stop, Restart](#start-stop-restart)
- [Environment Configuration](#environment-configuration)
- [Using the App](#using-the-app)
- [AI Workflow Recipes](#ai-workflow-recipes)
- [IoT Workflow Guide](#iot-workflow-guide)
- [LLM Providers](#llm-providers)
- [Agent File Writes](#agent-file-writes)
- [Data, Migrations, and Safety](#data-migrations-and-safety)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)

## What You Can Build

Use Agent Flow for practical agentic workflows such as:

- **Developer delivery loop** — requirements → project scan → architecture → code generation → QA → docs.
- **Repository audit** — scan codebase context, identify risks, produce review artifacts, and stage fixes.
- **Documentation sprint** — turn a prompt into README sections, usage guides, and release notes.
- **IoT home automation plan** — camera/sensor source → AI interpretation → safety review → dry-run or approved device action.
- **Enterprise operations pipeline** — telemetry gateway → classification agent → policy/safety agent → action dispatcher → final report.

## Current Capabilities

### AI Workflows

- Visual `Workflow builder` with chain and diagram views.
- Saved `Pipelines` page for reusable workflow definitions.
- `Live run show` for active run list, switching between runs, step logs, artifacts, and stop control.
- `Agent builder` for creating/editing agents, selecting LLM provider/model, skills, MCP metadata, and system prompt.
- AI workflow assistant that builds workflow structures from a prompt using preset roles and agent templates.
- Loop groups for iterative developer/QA cycles.
- Per-agent provider/model configuration.
- Safe file artifact handling with default review/staging mode.

### IoT Workflows

- Optional `IoT Pipelines` page controlled by `IOT_ENABLED`.
- Adapter catalog explaining what is real, what is gateway-backed, and what is configuration-only.
- Wi‑Fi/HTTP discovery for explicit hosts or small CIDR ranges.
- macOS Bluetooth inventory for known devices.
- Source read/test endpoint for allowlisted HTTP sources.
- Dry-run device action endpoint for safe validation.
- Approved real HTTP action endpoint gated by `IOT_DEVICE_ACTIONS_ENABLED` and `IOT_ALLOWED_HOSTS`.
- MQTT, RTSP, and Bluetooth control are represented as gateway-backed integrations instead of fake direct control.

### Runtime and Operations

- FastAPI backend on `http://localhost:8787/api`.
- React/Vite frontend on `http://localhost:5173`.
- SQLite state with migration tracking.
- Makefile lifecycle commands that preserve data.
- CORS allowlist and deny-by-default outbound action gates.

## How It Works

```text
Prompt / saved pipeline
        │
        ▼
Workflow builder ──► ordered agent steps ──► FastAPI runner
        │                                      │
        │                                      ├─ LLM provider call
        │                                      ├─ workspace context for agents
        │                                      ├─ IoT context for IoT steps
        │                                      ├─ file block staging/writes
        │                                      └─ NDJSON live events
        ▼
Pipelines + run history stored in SQLite
```

For IoT:

```text
Discovery / manual config
        │
        ▼
IoT source or action catalog
        │
        ├─ source read/test
        ├─ dry-run command
        └─ approved command, only when explicitly enabled and allowlisted
```

## Installation

### Requirements

- Python 3.9+
- Node.js 18+
- npm
- Optional: Ollama running locally if you want local models
- Optional: real provider keys for OpenAI, Gemini, or Claude

### Fresh Setup

```bash
git clone https://github.com/me7media/agent-flow.git
cd agent-flow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
cp .env.example .env
```

Open `.env`, set the provider keys you need, and keep unsafe controls disabled until you intentionally need them.

### First Run

```bash
make start
```

Open:

- UI: `http://localhost:5173`
- API health: `http://localhost:8787/api/health`

## Start, Stop, Restart

The Makefile is the recommended way to run the full app locally. It does not delete SQLite data.

```bash
make start    # apply pending migrations, start API + UI in the background
make stop     # stop API + UI, preserve app/data/agent_flow.sqlite3
make restart  # stop, apply pending migrations, start again
make status   # show API/UI process status and log locations
make logs     # tail .runtime/api.log and .runtime/ui.log
make migrate  # apply only unapplied SQL migrations
make api      # start only the API
make ui       # start only the UI
```

Manual alternatives:

```bash
npm run dev       # starts API + UI in one foreground process
npm run client    # Vite only
python run.py     # FastAPI only
```

## Environment Configuration

`.env` is for boot-time and system-level controls. Workflow-agent provider settings can also be edited from the `Settings` page and are stored in SQLite.

```env
PORT=8787

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
DEFAULT_LLM_PROVIDER=openai

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1

GEMINI_API_KEY=
GEMINI_MODEL=gemini-1.5-flash

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-5-sonnet-latest

WORKSPACE_ROOT=./workspace
AGENT_ALLOW_DIRECT_FILE_WRITES=false

IOT_ENABLED=true
IOT_DEVICE_ACTIONS_ENABLED=false
IOT_ALLOWED_HOSTS=
IOT_DISCOVERY_MAX_HOSTS=32

CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
HTTP_ACTION_ALLOWED_HOSTS=

EMAIL_ACTION_ENABLED=false
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_USER=
EMAIL_PASS=
EMAIL_FROM="Agent Flow <agent-flow@example.com>"
EMAIL_SECURE=false
```

### Important Flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `IOT_ENABLED` | `true` | Shows/hides IoT UI and enables/disables `/api/iot/*`. |
| `IOT_DEVICE_ACTIONS_ENABLED` | `false` | Allows real IoT HTTP actions when true; dry-run otherwise. |
| `IOT_ALLOWED_HOSTS` | empty | Comma-separated hosts/IPs allowed for IoT source reads and device actions. |
| `IOT_DISCOVERY_MAX_HOSTS` | `32` | Safety limit for network discovery scans. |
| `HTTP_ACTION_ALLOWED_HOSTS` | empty | Comma-separated hosts/IPs allowed for generic HTTP action calls. |
| `EMAIL_ACTION_ENABLED` | `false` | Enables real SMTP email action calls. |
| `AGENT_ALLOW_DIRECT_FILE_WRITES` | `false` | Legacy fallback; runtime Settings controls direct/review mode. |

## Using the App

### 1. Workflow Builder

Use `Workflow builder` to create and run an AI pipeline.

1. Enter a workflow name and workspace root.
2. Describe the task in the large task box.
3. Drag agents into the chain or use the AI workflow assistant.
4. Open a step to tune prompt, provider/model, loops, and IoT bindings.
5. Use loop groups for repeated agent ranges such as developer ↔ QA.
6. Click `Run live`.
7. Watch events and artifacts in `Live run show`.

### 2. Pipelines

Use `Pipelines` to load or delete saved workflows.

- Pipelines are stored in SQLite.
- Default pipelines are seeded automatically.
- If the page shows no pipelines, check that the API is running and `GET /api/flows` returns data.

### 3. Live Run Show

Use `Live run show` to supervise active and completed runs.

- See all current runs in the left list.
- Switch between running pipelines.
- Stop a run from the UI.
- Inspect step outputs and generated artifacts.

### 4. Agent Builder

Use `Agent builder` to create specialized agents.

1. Add a name and role.
2. Select provider and model.
3. Add skills and MCP metadata.
4. Add a precise system prompt.
5. Save the agent.
6. Reuse it in Workflow builder or IoT Pipelines.

### 5. Settings

Use `Settings` for runtime behavior.

- Change file write mode: staged review vs direct writes.
- Configure agent LLM providers and custom OpenAI-compatible endpoints.
- Store provider keys locally in SQLite; masked keys are preserved when editing settings.

## AI Workflow Recipes

### Recipe: Build a Feature Safely

Prompt:

```text
Build a FastAPI export endpoint with tests and README notes. Use a developer → QA loop and stage files for review.
```

Recommended flow:

1. Requirements Analyst
2. Project Scanner
3. Architecture Agent
4. Developer Agent
5. QA Agent
6. Documentation Writer
7. Final Assembler

Recommended settings:

- File write mode: `Stage under agent-flow-output/generated`
- Developer model: stronger cloud/local coding model
- QA model: cheaper model is often enough

### Recipe: Audit a Codebase

Prompt:

```text
Audit this project for incomplete code, unsafe defaults, missing tests, and production risks. Produce prioritized fixes.
```

Recommended flow:

1. Project Scanner
2. Security Reviewer
3. Architecture Agent
4. QA Agent
5. Documentation Writer

### Recipe: Generate Documentation

Prompt:

```text
Create a polished product README with setup, usage, examples, API routes, testing, and troubleshooting.
```

Recommended flow:

1. Requirements Analyst
2. Documentation Writer
3. QA Agent
4. Final Assembler

## IoT Workflow Guide

IoT is optional. Disable it completely with:

```env
IOT_ENABLED=false
```

When disabled:

- `IoT Pipelines` is hidden in the sidebar.
- IoT agents, skills, MCP metadata, and flows are filtered from public registry responses.
- `/api/iot/*` returns 404.

### What Works Directly

| Transport | Discovery | Read source | Execute action | Notes |
| --- | --- | --- | --- | --- |
| Wi‑Fi / HTTP | Yes | Yes | Yes, when enabled | Requires host in `IOT_ALLOWED_HOSTS`. |
| Bluetooth | Known-device inventory on macOS | Gateway required | Gateway required | Direct BLE control is OS/device specific. |
| MQTT | Gateway required | Gateway required | Gateway required | Use an HTTP/MQTT bridge or future MQTT adapter. |
| RTSP camera | Manual/gateway config | Gateway required | Not applicable | Use a camera/vision gateway for frames. |

### IoT Setup Steps

1. Keep real actions disabled first:

   ```env
   IOT_DEVICE_ACTIONS_ENABLED=false
   ```

2. Add trusted devices/gateways:

   ```env
   IOT_ALLOWED_HOSTS=DEVICE_LAN_IP,HOME_AUTOMATION_HOST
   ```

3. Restart the app:

   ```bash
   make restart
   ```

4. Open `IoT Pipelines`.
5. Use `Connectivity & discovery` for Wi‑Fi/HTTP hosts or Bluetooth inventory.
6. Add discovered HTTP devices as sources.
7. Save the IoT catalog.
8. Click `Read / test source` on sources.
9. Create actions for devices or gateways.
10. Test every action with `Dry run` first.
11. Only after validating hardware behavior, enable real actions:

    ```env
    IOT_DEVICE_ACTIONS_ENABLED=true
    ```

12. Restart and use `Execute approved` only for trusted actions.

### Example: Wi‑Fi Smart Plug On → 10s → Off

Use this for a real outlet only after you know its local network address and protocol. Replace every uppercase value with your own device data.

1. Find likely devices:

   ```bash
   arp -a
   curl -s http://localhost:8787/api/iot/discover \
     -H 'Content-Type: application/json' \
     -d '{"transport":"wifi/http","hosts":["DEVICE_LAN_IP"],"ports":["80","8080","8123","9999"]}' \
     | python3 -m json.tool
   ```

2. Allowlist only the device/gateway IP:

   ```env
   IOT_DEVICE_ACTIONS_ENABLED=true
   IOT_ALLOWED_HOSTS=DEVICE_LAN_IP
   ```

3. Register an action in `IoT Pipelines`.

   Tasmota:

   ```json
   {
     "id": "smart-plug-action",
     "name": "Smart plug",
     "kind": "smart_plug",
     "transport": "wifi/http",
     "endpoint": "http://DEVICE_LAN_IP",
     "adapter": "tasmota",
     "commands": ["turn_on", "turn_off"],
     "requiresApproval": true,
     "enabled": true
   }
   ```

   Shelly relay:

   ```json
   {
     "endpoint": "http://DEVICE_LAN_IP",
     "adapter": "shelly",
     "commands": ["turn_on", "turn_off"]
   }
   ```

   Custom HTTP gateway:

   ```json
   {
     "adapter": "custom",
     "commandMap": {
       "turn_on": {"method": "PUT", "path": "/api/device/state", "json": {"state": "on", "device": "{{actionId}}"}},
       "turn_off": {"method": "PUT", "path": "/api/device/state", "json": {"state": "off", "device": "{{actionId}}"}}
     }
   }
   ```

4. Dry-run first:

   ```bash
   curl -s -X POST http://localhost:8787/api/iot/actions/test \
     -H 'Content-Type: application/json' \
     -d '{"actionId":"smart-plug-action","command":"turn_on"}' \
     | python3 -m json.tool
   ```

5. Execute approved on/off:

   ```bash
   curl -s -X POST http://localhost:8787/api/iot/actions/execute \
     -H 'Content-Type: application/json' \
     -d '{"actionId":"smart-plug-action","command":"turn_on","approved":true,"dryRun":false}' \
     | python3 -m json.tool

   sleep 10

   curl -s -X POST http://localhost:8787/api/iot/actions/execute \
     -H 'Content-Type: application/json' \
     -d '{"actionId":"smart-plug-action","command":"turn_off","approved":true,"dryRun":false}' \
     | python3 -m json.tool
   ```

### Example: Camera Gesture → Gate Command

Goal: detect an approved hand gesture and prepare a gate command.

Recommended flow:

1. IoT Signal Agent — normalizes source metadata.
2. Vision Gesture Agent — interprets gesture intent and confidence.
3. IoT Safety Supervisor — rejects ambiguous or unsafe actions.
4. IoT Device Manager — prepares dry-run or approved command.

Safety defaults:

- Gate action should require approval.
- Device host must be in `IOT_ALLOWED_HOSTS`.
- Real action is blocked unless `IOT_DEVICE_ACTIONS_ENABLED=true`.

### Example: Enterprise Sensor → Incident Pipeline

Goal: classify sensor telemetry and route follow-up actions.

Recommended flow:

1. IoT Signal Agent
2. Classification / Domain Agent
3. Safety or Policy Reviewer
4. API Integration Agent
5. Final Assembler

Use a gateway endpoint for MQTT/industrial protocols and register that gateway as a Wi‑Fi/HTTP source or action.

## LLM Providers

Supported provider choices:

- `mock` — built-in deterministic local mock for demos/tests.
- `openai` — OpenAI Responses API.
- `ollama` — local Ollama `/api/generate` endpoint.
- `gemini` — Gemini generateContent API.
- `anthropic` / `claude` — Anthropic Messages API.
- Custom OpenAI-compatible providers via runtime provider settings.

### What Is `mock-model`?

`mock-model` is not a real external AI model. It is a deterministic built-in provider used for local demos, tests, and offline development. It can emit example file blocks so the runner and tests can verify file-generation behavior without network access.

Use real providers when you need real reasoning or production-quality outputs.

## Agent File Writes

Agents can create or edit files only when their model output contains file blocks:

````markdown
```file path="src/example.js"
export function example() {
  return true;
}
```
````

The runner supports two modes:

- **Review/staging mode** — default; writes generated files under `agent-flow-output/generated/...`.
- **Direct write mode** — writes project-relative files directly; use only for trusted workflows.

Safety rules:

- Paths must be relative to `WORKSPACE_ROOT`.
- Path traversal is blocked.
- Write size is limited.
- Markdown artifacts are still written for agents that produce outputs but no file blocks.

## Data, Migrations, and Safety

### SQLite Data

Runtime state is stored in:

```text
app/data/agent_flow.sqlite3
```

This file is ignored by git and is not removed by Makefile commands.

### Migrations

SQL migrations live in:

```text
app/migrations/
```

Migrations are applied automatically before state reads/writes and by:

```bash
make migrate
```

`make migrate` only applies pending migrations tracked in `schema_migrations`; it does not wipe or recreate the database.

### Public Workspace Browser

There is no public `Workspace / Git` UI page and no public `/api/workspace/*` or `/api/git/info` browser routes. Workflow runs still use `WORKSPACE_ROOT` internally for agent context and generated artifacts.

### Auth / ACL

This project currently expects trusted local/network deployment. If exposing beyond a trusted local environment, put it behind authentication, TLS, and network access controls.

## API Reference

### Core

| Method | Route | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health, providers, feature flags, public settings. |
| `GET` | `/api/registry` | Agents, skills, MCP metadata, providers, settings. |
| `GET` | `/api/providers` | Provider list and configured status. |
| `GET` | `/api/settings` | Public runtime settings with masked secrets. |
| `PUT` | `/api/settings` | Save runtime settings. |

### Agents and Workflows

| Method | Route | Description |
| --- | --- | --- |
| `GET` | `/api/agents` | List agents. |
| `POST` | `/api/agents` | Create/update an agent. |
| `GET` | `/api/flows` | List saved pipelines. |
| `POST` | `/api/flows` | Save a pipeline. |
| `DELETE` | `/api/flows/{id}` | Delete a pipeline. |
| `POST` | `/api/flows/run` | Run a pipeline and return logs. |
| `POST` | `/api/flows/run/stream` | Run a pipeline with NDJSON live events. |
| `GET` | `/api/runs` | Recent run history. |

### IoT

| Method | Route | Description |
| --- | --- | --- |
| `GET` | `/api/iot/pipelines` | Built-in and saved IoT pipelines. |
| `GET` | `/api/iot/catalog` | IoT sources and actions. |
| `GET` | `/api/iot/adapters` | Adapter capabilities and device-action status. |
| `POST` | `/api/iot/discover` | Wi‑Fi/HTTP scan or Bluetooth inventory. |
| `POST` | `/api/iot/signals` | Normalize an incoming IoT signal payload. |
| `POST` | `/api/iot/sources/read` | Read/test a configured source. |
| `POST` | `/api/iot/actions/test` | Dry-run an IoT action command. |
| `POST` | `/api/iot/actions/execute` | Execute an approved IoT action when real actions are enabled. |

### External Actions

| Method | Route | Description |
| --- | --- | --- |
| `POST` | `/api/actions/http` | Generic HTTP action, gated by `HTTP_ACTION_ALLOWED_HOSTS`. |
| `POST` | `/api/actions/email/send` | SMTP email action, gated by `EMAIL_ACTION_ENABLED`. |

## Testing

Run all tests:

```bash
npm test
```

Build frontend:

```bash
npm run build
```

Compile backend modules:

```bash
.venv/bin/python -m compileall app
```

Smoke check API and pipelines:

```bash
.venv/bin/python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    for path in ['/api/health', '/api/settings', '/api/flows', '/api/iot/adapters']:
        response = client.get(path)
        print(path, response.status_code)
        assert response.status_code < 400, response.text
    assert len(client.get('/api/flows').json()) > 0
print('smoke ok')
PY
```

## Troubleshooting

### Pipelines Page Shows “No pipelines yet”

1. Check API is running:

   ```bash
   make status
   ```

2. Check backend logs:

   ```bash
   make logs
   ```

3. Verify API data:

   ```bash
   curl http://localhost:8787/api/flows
   ```

4. If the API was running during code changes, restart it:

   ```bash
   make restart
   ```

### API Fails During Startup

Run:

```bash
.venv/bin/python -m compileall app
npm test
```

Then inspect `.runtime/api.log`.

### Real IoT Action Does Not Execute

Check all of these:

- `IOT_ENABLED=true`
- `IOT_DEVICE_ACTIONS_ENABLED=true`
- Device host is present in `IOT_ALLOWED_HOSTS`
- Action transport includes `http`
- Action endpoint is reachable from the machine running the API
- Action was executed with approval from the UI/API

If any condition is missing, the app will return a dry-run, approval-required, gateway-required, or blocked response.

### HTTP or Email Action Is Blocked

This is expected by default.

- Add trusted hosts to `HTTP_ACTION_ALLOWED_HOSTS` for generic HTTP actions.
- Set `EMAIL_ACTION_ENABLED=true` and configure SMTP for email actions.

### Agent Does Not Create Files

Check:

- Agent output contains a valid file block.
- The agent has developer/file-write-like skills.
- `WORKSPACE_ROOT` is correct.
- File write mode is `review` or `direct` as intended.
- Review-mode files appear under `agent-flow-output/generated/...`.

## Project Structure

```text
app/
  main.py                 FastAPI API routes, scheduler restore, streaming runs
  runner.py               Workflow execution, prompts, artifacts, file blocks
  llm.py                  Provider routing for mock/OpenAI/Ollama/Gemini/Claude/custom
  iot.py                  IoT domain defaults, agents, skills, demo flows
  iot_runtime.py          IoT adapters, discovery, source reads, safe actions
  settings_service.py     Runtime settings normalization and secret masking
  database.py             SQLite connection and migration runner
  storage.py              State read/write compatibility layer
  workspace.py            Internal safe workspace file helpers
  migrations/             SQL migrations
src/
  main.jsx                App shell, workflow builder, live run, agent builder
  iotPipelinesPage.jsx    IoT discovery, catalog, action testing, IoT assistant
  settingsPage.jsx        Agent execution and LLM provider settings
tests/
  test_*.py               Backend/domain tests
  workflowAssistant.test.mjs  Workflow assistant tests
Makefile                  Local lifecycle commands
```

## Default URLs

- UI: `http://localhost:5173`
- API: `http://localhost:8787/api`
- Health: `http://localhost:8787/api/health`
