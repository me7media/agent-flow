# Agent Flow Python

Full Agent Flow project with the original React/Vite UI and a Python/FastAPI backend. The UI is kept functionally the same as the Node version and still talks to the API through `http://localhost:8787/api`.

## What Was Ported

- Original React/Vite UI from the Node project.
- Registry endpoints for agents, skills, MCP connectors and flows.
- JSON file storage under `app/data/db.json`.
- Flow execution with chain loops, visible loop groups and per-step loops.
- NDJSON streaming from `/api/flows/run/stream`.
- Workspace scan/read/write helpers with path traversal protection.
- Safe git info endpoint using read-only git commands.
- Mock LLM provider when `OPENAI_API_KEY` is empty.
- OpenAI Responses API provider when `OPENAI_API_KEY` is configured.
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
WORKSPACE_ROOT=./workspace
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_USER=
EMAIL_PASS=
EMAIL_FROM="Agent Flow <agent-flow@example.com>"
EMAIL_SECURE=false
AGENT_ALLOW_DIRECT_FILE_WRITES=false
```

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

The original Node backend uses a JSON DB and mostly stateless services, so the Python version mirrors that architecture instead of introducing a database or worker queue. Cron scheduling is kept in-process, matching the original behavior where saved cron flows are scheduled after they are posted to the API.
