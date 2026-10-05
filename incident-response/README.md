# Incident Responder

Receives Grafana webhook alerts for the Order Tracker service and triages them with a headless Claude Code agent.

## Run it

```bash
cd incident-response
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

The `claude` CLI must be on `PATH` and already logged in (this service shells out to it; it does not handle auth). The main Order Tracker stack (`docker compose up --build -d --wait` in the repo root) should already be running, since the agent inspects and rebuilds it.

Point a Grafana contact point (webhook type) at `http://<host>:8001/alerts`.

## What it does

`POST /alerts` accepts a Grafana (Alertmanager-shaped) webhook payload — a JSON body with an `alerts` list, each with `labels`/`annotations`. For each alert:

1. Creates `incidents/<timestamp>-<alertname>/`.
2. Saves evidence into it: `payload.json` (the raw alert), `endpoint.txt` (the affected route, from the `http_route` label or sniffed out of the annotations), `logs.txt` (recent app logs — queried from Loki, falling back to `docker compose logs app --since 10m` if Loki isn't reachable), and `traces.json` (a Tempo TraceQL search scoped to that route).
3. Builds a prompt and starts `claude -p "<prompt>"` in the repo root, in the background (the HTTP response returns `202` immediately, before the agent finishes).
4. The agent's full output streams to `agent_response.md` in the incident folder; the prompt itself is saved alongside as `agent_prompt.txt`.

If the alert carries the label `test="true"`, the prompt tells the agent this is only a drill: acknowledge it, change nothing, and give a one-line final answer. Otherwise the prompt asks it to read the evidence, find and fix the root cause in `app/`, add or update a test, run `uv run --frozen pytest -q`, rebuild with `docker compose up --build -d --wait`, verify the fix against the real endpoint, and write `report.md` into the incident folder.

The agent is launched with `--allowedTools` restricted to `Read`, `Edit`, `Write`, and a Bash allowlist of `uv`, `docker compose`, `curl`, and `git status`/`diff`/`add`/`commit` — notably **not** a blanket `git *`, so `git push` is never an allowed command. The prompt also explicitly tells it never to push or delete files.

## Testing it

Send a webhook shaped like Grafana's, with a `test="true"` label so it takes the safe, no-op path:

```bash
curl -X POST http://localhost:8001/alerts \
  -H "Content-Type: application/json" \
  -d @sample-alert.json
```

Then check `incident-response/incidents/<new-folder>/agent_response.md` for the agent's one-line acknowledgment.

To test the real incident-response path, drop the `test` label (or send an alert from the actual "Order API 5xx errors" rule) and the agent will attempt an actual fix.

## Config

| Env var | Default | Purpose |
| --- | --- | --- |
| `LOKI_URL` | `http://127.0.0.1:3100` | Loki base URL for log evidence |
| `TEMPO_URL` | `http://127.0.0.1:3200` | Tempo base URL for trace evidence |
| `CLAUDE_BIN` | `claude` | Path to the Claude Code CLI |
