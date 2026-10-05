# Order Tracker

A small order tracking app for the AI Dev Tools Zoomcamp observability homework. It includes a web page, API, tests, and a Docker Compose setup. You add telemetry, alerts, and an incident responder in Homework 4.

The main user flow is creating an order and checking its status. Three sample orders are created on first startup.

## Run it

You need Docker with Compose. To run the tests, you also need Python 3.11+ and `uv`.

```bash
docker compose up --build -d --wait
```

Open <http://127.0.0.1:8000>. The API is at `/api/orders`, and the health check is at `/healthz`. Data is stored in a Docker volume and survives container recreation.

If port 8000 is occupied, set `ORDER_TRACKER_PORT`, for example:

```bash
ORDER_TRACKER_PORT=18080 docker compose up --build -d --wait
```

Run tests with `uv run --frozen pytest -q`. Stop the app with `docker compose down`. Add `-v` only if you also want to delete the order data.

## Observability

`docker compose up` also starts an OpenTelemetry Collector, Prometheus, Loki, Tempo, and Grafana (config under `observability/`). The app exports traces, metrics, and logs via OTLP/gRPC to the Collector, which fans them out: metrics to Prometheus, logs to Loki, traces to Tempo.

- Grafana: <http://127.0.0.1:3000> (anonymous Admin access, no login) — the "Order Tracker" dashboard is provisioned automatically, with Prometheus/Loki/Tempo datasources and trace-to-logs correlation.
- Prometheus: <http://127.0.0.1:9090>
- Loki: <http://127.0.0.1:3100>
- Tempo: <http://127.0.0.1:3200>

Set `OTEL_CONSOLE_EXPORT=true` (env var, picked up by `compose.yaml`) to also print all three signals to `docker compose logs app`, alongside the OTLP export.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Web page |
| GET | `/healthz` | Database health check |
| GET | `/api/orders` | List orders |
| POST | `/api/orders` | Create an order |
| GET | `/api/orders/{id}` | Check an order |
| PATCH | `/api/orders/{id}` | Change an order status |

The app uses SQLite to keep setup small. Run one app container at a time. The course exercise is about detecting and handling an incident, not scaling the database.

## Homework 4 – what was built

**Architecture:** the app exports traces, metrics, and logs via OTLP/gRPC to an OpenTelemetry Collector, which fans them out — metrics to Prometheus, logs to Loki, traces to Tempo — all visualized in Grafana. A Grafana alert rule watches the request metric for 5xx responses and, when it fires, a notification policy routes it to a webhook contact point pointed at a small FastAPI service (the "incident responder"). That service collects evidence (the alert payload, recent logs, related traces) and starts a headless Claude Code agent (`claude -p`) in the background to investigate, fix, and verify the issue.

**How to run it:**

```bash
docker compose up --build -d --wait
```

This starts the app and the whole observability stack. Grafana is at <http://127.0.0.1:3000> (anonymous admin, no login). Separately, start the incident responder:

```bash
cd incident-response
uv run uvicorn app.main:app --port 8001
```

(it needs the `claude` CLI on `PATH` and logged in; see `incident-response/README.md`).

**Where things live:**
- Alert rule and notification routing: `observability/grafana/provisioning/alerting/rules.yaml` (the "Order API 5xx errors" rule) and `notifications.yaml` (the `incident-responder` webhook contact point and its routing policy).
- The responder service: `incident-response/` (`app/main.py`, `README.md`).
- Incident evidence, one folder per alert: `incident-response/incidents/<timestamp>-<alertname>/` — `payload.json`, `endpoint.txt`, `logs.txt`, `traces.json`, `agent_prompt.txt`, `agent_response.md`, and the agent's own `report.md`.

**The incident:** `express-1002` (an order seeded on the last day of the previous month) returned a 500 on `GET /api/orders/{order_id}`. Root cause: `order_detail()` computed the express delivery estimate with `placed_at.replace(day=placed_at.day + 2)`, which doesn't roll over into the next month and raises `ValueError` for any express order placed in the last two days of a month. The headless agent found this, fixed it with `placed_at + timedelta(days=2)`, added regression tests, ran the test suite, rebuilt the stack, and verified the endpoint — all in commit `36663b9`.

**What went wrong first, honestly:** the first few runs correctly diagnosed and fixed the bug via the agent's `Edit`/`Write` tools, but never got to run anything — `uv run --frozen pytest`, `docker compose up --build`, and `curl` were all blocked. The cause: the agent's `--allowedTools` only allowlisted the `Bash` tool, but on this Windows machine Claude Code can route shell execution through a separate `PowerShell` tool instead, which wasn't allowlisted at all — so every verification step silently failed with "this session can't approve commands." That's fixed in commit `f98ae2b`, which mirrors every allowed command pattern for both tools. The first attempt's (correct, but unverified) diagnosis and fix are kept as `incident-response/incidents/first-attempt-fix.patch` for reference, alongside the full evidence trail from every run, including the blocked ones.

**Known limitation:** the allowlist's `uv *` pattern is broad — `uv run` can execute arbitrary Python (e.g. `uv run python -c "..."`), not just `pytest`/`sync`. It's intentionally kept that wide for this exercise, but a tighter policy would scope it to specific subcommands.
