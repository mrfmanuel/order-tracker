"""Grafana webhook receiver that triages Order Tracker incidents.

POST /alerts accepts a Grafana (Alertmanager-shaped) webhook payload,
collects evidence for each alert, and kicks off a headless Claude Code
agent in the background to look at it. The HTTP response returns 202
immediately — it never waits for the agent to finish.
"""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

APP_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = APP_DIR.parent
REPO_ROOT = SERVICE_ROOT.parent
INCIDENTS_DIR = SERVICE_ROOT / "incidents"

LOKI_URL = os.getenv("LOKI_URL", "http://127.0.0.1:3100")
TEMPO_URL = os.getenv("TEMPO_URL", "http://127.0.0.1:3200")
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
EVIDENCE_WINDOW_MINUTES = 10

# Only these commands may be run by the agent's Bash tool. Deliberately not a
# blanket "git *" — git is limited to read-only/stage/commit, never push.
ALLOWED_TOOLS = (
    "Read Edit Write "
    "Bash(uv *) "
    "Bash(docker compose *) "
    "Bash(curl *) "
    "Bash(git status) Bash(git status *) "
    "Bash(git diff) Bash(git diff *) "
    "Bash(git add *) "
    "Bash(git commit *)"
)

app = FastAPI(title="Incident Responder")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return slug or "alert"


def extract_route(labels: dict[str, Any], annotations: dict[str, Any]) -> str | None:
    if labels.get("http_route"):
        return labels["http_route"]
    for key in ("summary", "description"):
        match = re.search(r"/api/\S+", annotations.get(key, ""))
        if match:
            return match.group(0).rstrip(".,)")
    return None


def fetch_loki_logs() -> str:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=EVIDENCE_WINDOW_MINUTES)
    params = {
        "query": '{service_name="order-tracker"}',
        "start": str(int(start.timestamp() * 1_000_000_000)),
        "end": str(int(end.timestamp() * 1_000_000_000)),
        "limit": "500",
        "direction": "forward",
    }
    try:
        resp = httpx.get(f"{LOKI_URL}/loki/api/v1/query_range", params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        lines = []
        for stream in data.get("data", {}).get("result", []):
            stream_labels = stream.get("stream", {})
            for ts, line in stream.get("values", []):
                lines.append((int(ts), f"[{stream_labels.get('severity_text', '?')}] {line}"))
        lines.sort(key=lambda item: item[0])
        if lines:
            return "\n".join(line for _, line in lines)
        return "(Loki returned no log lines in the last %dm)" % EVIDENCE_WINDOW_MINUTES
    except Exception as exc:  # Loki unreachable or query failed -> fall back.
        fallback_header = f"(Loki query failed: {exc}; falling back to `docker compose logs`)\n"
        try:
            result = subprocess.run(
                ["docker", "compose", "logs", "app", "--since", f"{EVIDENCE_WINDOW_MINUTES}m"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return fallback_header + result.stdout + result.stderr
        except Exception as fallback_exc:
            return fallback_header + f"(docker compose logs also failed: {fallback_exc})"


def fetch_tempo_traces(route: str | None) -> str:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=EVIDENCE_WINDOW_MINUTES)
    query = '{resource.service.name="order-tracker"}'
    if route:
        escaped = route.replace('"', '\\"')
        query = f'{{resource.service.name="order-tracker" && span.http.route="{escaped}"}}'
    params = {
        "q": query,
        "start": str(int(start.timestamp())),
        "end": str(int(end.timestamp())),
        "limit": "20",
    }
    try:
        resp = httpx.get(f"{TEMPO_URL}/api/search", params=params, timeout=5)
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Tempo query failed: {exc}", "query": query}, indent=2)


def build_prompt(incident_dir: Path, alertname: str, is_test: bool, route: str | None) -> str:
    rel = incident_dir.relative_to(REPO_ROOT)
    if is_test:
        return (
            f"This is a TEST notification (label test=\"true\") from the Order Tracker "
            f"service's Grafana alerting, alert name \"{alertname}\". It is only a drill to "
            f"verify the incident-response pipeline is wired up correctly.\n\n"
            f"Do not investigate anything. Do not change, add, or delete any files. Do not run "
            f"any commands.\n\n"
            f"Acknowledge that you received this test alert, then end your reply with exactly "
            f"one final line in this form:\n"
            f"FINAL ANSWER: Test alert acknowledged; no action taken.\n"
        )
    return (
        f"A Grafana alert fired for the Order Tracker service: \"{alertname}\""
        + (f", affecting route {route}" if route else "")
        + ".\n\n"
        f"Incident evidence has already been collected in {rel}/:\n"
        f"  - payload.json  — the raw Grafana webhook payload\n"
        f"  - endpoint.txt  — the affected API route (if one could be determined)\n"
        f"  - logs.txt      — recent app logs (from Loki, or `docker compose logs app` as a fallback)\n"
        f"  - traces.json   — related traces queried from Tempo\n\n"
        f"Please:\n"
        f"1. Read that evidence.\n"
        f"2. Find the root cause in the application code (under app/).\n"
        f"3. Fix the root cause.\n"
        f"4. Add or update a test under tests/ that would have caught this.\n"
        f"5. Run the test suite with `uv run --frozen pytest -q` and make sure it passes.\n"
        f"6. Rebuild and restart the stack with `docker compose up --build -d --wait`.\n"
        f"7. Verify the previously-failing request now works (e.g. with curl against the "
        f"affected endpoint).\n"
        f"8. Write a short incident report to {rel}/report.md: root cause, the fix, and the "
        f"verification output.\n\n"
        f"You may use `git status`, `git diff`, `git add`, and `git commit` if you want to "
        f"commit the fix. Never run `git push`. Never delete any files.\n"
    )


def launch_agent(incident_dir: Path, prompt: str) -> None:
    (incident_dir / "agent_prompt.txt").write_text(prompt, encoding="utf-8")
    output_path = incident_dir / "agent_response.md"
    with open(output_path, "w", encoding="utf-8") as output_file:
        subprocess.Popen(
            [
                CLAUDE_BIN,
                "-p",
                prompt,
                "--allowedTools",
                ALLOWED_TOOLS,
                "--permission-prompts",
                "none",
            ],
            cwd=REPO_ROOT,
            stdout=output_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )


def handle_alert(alert: dict[str, Any]) -> dict[str, Any]:
    labels = alert.get("labels", {}) or {}
    annotations = alert.get("annotations", {}) or {}
    alertname = labels.get("alertname", "alert")
    is_test = str(labels.get("test", "")).lower() == "true"
    route = extract_route(labels, annotations)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    incident_dir = INCIDENTS_DIR / f"{timestamp}-{slugify(alertname)}"
    incident_dir.mkdir(parents=True, exist_ok=True)

    (incident_dir / "payload.json").write_text(json.dumps(alert, indent=2), encoding="utf-8")
    (incident_dir / "endpoint.txt").write_text((route or "(could not be determined)") + "\n", encoding="utf-8")
    (incident_dir / "logs.txt").write_text(fetch_loki_logs(), encoding="utf-8")
    (incident_dir / "traces.json").write_text(fetch_tempo_traces(route), encoding="utf-8")

    prompt = build_prompt(incident_dir, alertname, is_test, route)
    launch_agent(incident_dir, prompt)

    return {
        "alertname": alertname,
        "is_test": is_test,
        "route": route,
        "incident_dir": str(incident_dir.relative_to(REPO_ROOT)),
    }


@app.post("/alerts", status_code=202)
async def receive_alert(request: Request) -> JSONResponse:
    payload = await request.json()
    alerts = payload.get("alerts") if isinstance(payload, dict) else None
    if not alerts:
        # Not an Alertmanager-wrapped payload — treat the body itself as one alert.
        alerts = [payload]

    handled = [handle_alert(alert) for alert in alerts]
    return JSONResponse(status_code=202, content={"accepted": len(handled), "incidents": handled})


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}
