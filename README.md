# Agent Flow Python

Full Agent Flow project with the original React/Vite UI and a Python/FastAPI backend. The UI is kept functionally the same as the Node version and still talks to the API through `http://localhost:8787/api`.

## What Was Ported

- Original React/Vite UI from the Node project.
- Workflow builder UI with chain and diagram views.
- AI workflow assistant that builds pipelines from a prompt using preset or generated agents.
- Pipelines page for saved workflow configurations.
- Registry endpoints for agents, skills, MCP connectors and flows.
- SQLite storage under `app/data/agent_flow.sqlite3`.
- SQL migrations under `app/migrations`.
- Flow execution with chain loops, visible loop groups and per-step loops.
- NDJSON streaming from `/api/flows/run/stream`.
- Workspace scan/read/write helpers with path traversal protection.
- Safe git info endpoint using read-only git commands.
- Mock LLM provider when `OPENAI_API_KEY` is empty.
- OpenAI Responses API provider when `OPENAI_API_KEY` is configured.
- Ollama, Gemini and Claude provider selection per agent.
- HTTP action and SMTP email action endpoints.

## Run Locally

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

You can also run only the backend with `python run.py` or only the UI with `npm run client`.

## Environment

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
AGENT_ALLOW_DIRECT_FILE_WRITES=false
```

Agents can choose `mock`, `openai`, `ollama`, `gemini` or `anthropic`/Claude in Agent builder or from the workflow step drawer. Ollama uses the local `OLLAMA_BASE_URL`; Gemini requires `GEMINI_API_KEY`; Claude requires `ANTHROPIC_API_KEY`.

When `AGENT_ALLOW_DIRECT_FILE_WRITES=false`, developer agents can still emit real `file` blocks, but the backend stages them under `agent-flow-output/generated/<agent>/` for review. When it is `true`, those same file blocks are written to their exact project-relative paths, including new folders.

## API Compatibility

The Python backend implements these routes:

- `GET /api/health`
- `GET /api/registry`
- `GET /api/agents`
- `POST /api/agents`
- `GET /api/flows`
- `POST /api/flows`
- `DELETE /api/flows/{id}`
- `POST /api/flows/run`
- `POST /api/flows/run/stream`
- `GET /api/runs`
- `POST /api/workspace/scan`
- `POST /api/workspace/read`
- `POST /api/workspace/write`
- `POST /api/git/info`
- `POST /api/actions/http`
- `POST /api/actions/email/send`

## Notes From The Port

The Python backend uses SQLite plus SQL migrations for project lifecycle data. Agent outputs, flow definitions and run history survive process restarts without relying on a hand-edited JSON database. Cron scheduling is still kept in-process, matching the original behavior where saved cron flows are scheduled after they are posted to the API.
