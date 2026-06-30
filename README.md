# Agent Flow Python

Agent Flow Python is a lightweight full-stack workflow builder for coordinating AI agents, local project work, and IoT-style signal/action pipelines. It keeps the original React/Vite UI and replaces the backend with FastAPI, SQLite, migrations, streaming run logs, and configurable LLM providers.

## Highlights

- React/Vite UI with `Workflow builder`, diagram view, `Live run show`, `Pipelines`, `Agent builder`, `IoT Pipelines`, `Settings`, and workspace tools.
- FastAPI backend at `http://localhost:8787/api`.
- SQLite lifecycle storage in `app/data/agent_flow.sqlite3` with SQL migrations in `app/migrations`.
- Per-agent LLM provider/model selection: Mock, OpenAI, Ollama, Gemini, Claude/Anthropic, and OpenAI-compatible custom providers.
- AI workflow assistant for building workflows from a prompt.
- IoT Pipelines for camera/microphone/sensor sources, controllable actions, IoT control agents, and safe dry-run device commands.
- Developer agents can create or edit real files from model-emitted `file` blocks.
- NDJSON live run streaming from `/api/flows/run/stream`.
- Workspace scan/read/write helpers with path traversal protection.
- Safe read-only git info endpoint.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
cp .env.example .env
npm run dev
```

Local URLs:

- UI: `http://localhost:5173`
- API health: `http://localhost:8787/api/health`

Run only one side:

```bash
npm run client
python run.py
```

## Project Structure

```text
app/
  main.py                 FastAPI routes and scheduling hooks
  runner.py               Workflow execution, prompts, artifacts, file blocks
  llm.py                  Provider routing for mock/openai/ollama/gemini/claude/custom
  iot.py                  IoT sources, actions, demo agents and demo pipelines
  settings_service.py     Runtime settings normalization and secret masking
  database.py             SQLite connection and migration runner
  migrations/             SQL migrations
src/
  main.jsx                App shell, workflow builder, live run, agent builder
  iotPipelinesPage.jsx    IoT catalog, IoT assistant, control agents, demo flows
  settingsPage.jsx        Agent execution and LLM provider settings
tests/                    Node and Python tests
```

## Configuration Model

Agent Flow separates system boot defaults from runtime workflow configuration.

### `.env`

Use `.env` for system fallback values and first boot defaults only:

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
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_USER=
EMAIL_PASS=
EMAIL_FROM="Agent Flow <agent-flow@example.com>"
EMAIL_SECURE=false
```

### Settings Page

The `Settings` page is for runtime agent behavior:

- **Agent execution** — direct file writes vs staged review mode, plus max parsed file blocks.
- **Agent LLM providers** — provider ID, display name, provider kind, default model, base URL, API key, enabled flag.

Workflow-agent provider settings are persisted in SQLite, so you do not need to edit `.env` for ordinary agent configuration.

### IoT Pipelines Page

IoT-specific runtime configuration lives in `IoT Pipelines`, not in global Settings:

- **IoT sources** — cameras, microphones, sensors, webhooks, files, or device telemetry over Wi‑Fi, Bluetooth, cable, HTTP, MQTT, RTSP, etc.
- **IoT actions** — device-like capabilities such as gate controllers, relays, locks, appliances, and allowed commands.
- **IoT control agents** — IoT-aware agents that can be opened in Workflow builder for signal handling, safety review, or device command preparation.
- **AI IoT assistant** — creates a workflow from a plain-language IoT scenario.

## What Is `mock-model`?

`mock-model` is not a real external AI model. It is the built-in deterministic mock LLM used for local demos, tests, and offline development. When an agent uses provider `mock` or a cloud provider is missing an API key, the backend can fall back to this mock behavior.

The mock provider is useful because it:

- requires no network and no API key;
- produces predictable outputs for tests;
- can emit example `file` blocks so developer-agent file writing can be tested safely;
- makes the app usable immediately after installation.

Use a real provider such as OpenAI, Ollama, Gemini, Claude, or a custom OpenAI-compatible endpoint when you want actual model reasoning.

## Agent File Writes

Developer-style agents are instructed to emit files in this format:

````markdown
```file path="src/example.js"
export function example() {
  return true;
}
```
````

The runner parses these blocks and writes them according to `Settings → Agent execution`:

- **Direct write to workspace** — creates/updates the exact project-relative files.
- **Stage under `agent-flow-output/generated`** — stores generated files for human review first.

All paths remain workspace-relative and are checked against path traversal.

## IoT Example

The built-in `IoT: Camera gesture → gate action` pipeline demonstrates:

1. Read metadata from a configured front-yard camera source.
2. Recognize a gesture and estimate confidence.
3. Run a safety supervisor step before physical-world action.
4. Prepare a dry-run gate command such as `open`, `close`, or `stop`.

Device execution is intentionally explicit and dry-run oriented by default. Real integrations should add approval, audit logs, and hardware-specific adapters before controlling physical devices.

## API Routes

Core:

- `GET /api/health`
- `GET /api/registry`
- `GET /api/providers`
- `GET /api/settings`
- `PUT /api/settings`

Agents and workflows:

- `GET /api/agents`
- `POST /api/agents`
- `GET /api/flows`
- `POST /api/flows`
- `DELETE /api/flows/{id}`
- `POST /api/flows/run`
- `POST /api/flows/run/stream`
- `GET /api/runs`

IoT:

- `GET /api/iot/pipelines`
- `GET /api/iot/catalog`
- `POST /api/iot/signals`
- `POST /api/iot/actions/test`

Workspace and actions:

- `POST /api/workspace/scan`
- `POST /api/workspace/read`
- `POST /api/workspace/write`
- `POST /api/git/info`
- `POST /api/actions/http`
- `POST /api/actions/email/send`

## Testing

Run all configured tests:

```bash
npm test
```

Run the production UI build:

```bash
npm run build
```

Useful backend smoke check:

```bash
.venv/bin/python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
for method, path, payload in [
    ("GET", "/api/health", None),
    ("GET", "/api/settings", None),
    ("GET", "/api/iot/pipelines", None),
    ("POST", "/api/flows/run", {"flow": [], "task": "smoke", "loops": 1}),
]:
    response = client.request(method, path, json=payload)
    print(method, path, response.status_code)
    assert response.status_code < 400, response.text
print("backend smoke ok")
PY
```

## Operational Notes

- SQLite data survives process restarts.
- Migrations are applied automatically before reading/writing state.
- Saved cron workflows are scheduled in-process when posted to the backend.
- API keys saved from Settings are stored locally in SQLite and masked when returned to the UI.
- IoT actions are domain/workflow objects, so they are managed from `IoT Pipelines`, not global Settings.
