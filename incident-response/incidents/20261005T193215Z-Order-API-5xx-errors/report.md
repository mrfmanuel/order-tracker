# Incident report: Order API 5xx errors

- **Alert:** Grafana "Order API 5xx errors", started 2026-10-05T19:32:10Z
- **Route:** `GET /api/orders/{order_id}`
- **Recurrence:** This is the fifth time this alert has fired today (see earlier incidents
  `20261005T192155Z`, `192430Z`, `192725Z`, `193035Z`). Each time it had the same cause.

## Evidence

- `logs.txt`: every failure is the same order: `[ERROR] order lookup for express-1002 -> 500` (4 times).
- `traces.json`: `get_order` traces from `order-tracker` on `/api/orders/{order_id}`, each
  with `errorCount: 1`. The trace search results don't include the exception details.

## Root cause

In the deployed code, `order_detail()` in `app/main.py` worked out the delivery estimate for
express orders like this:

```python
estimated_at = placed_at.replace(day=placed_at.day + 2)
```

`datetime.replace()` does not roll over into the next month. When the order was placed in
the last two days of a month, it raises `ValueError: day is out of range for month`.
`get_order` turns that error into an HTTP 500.

The seeded order `express-1002` is always created on the last day of the previous month
(today that is 2026-09-30). So every lookup of it fails.

**Why it keeps firing:** Earlier sessions had already written the fix and tests into the
working tree. But none of those sessions could run commands, so the container was never
rebuilt and still runs the broken code. The fix is still uncommitted (`M app/main.py`,
`M tests/test_api.py`).

## Fix (already in the working tree)

`app/main.py:61`:

```python
estimated_at = placed_at + timedelta(days=2)
```

`timedelta` arithmetic handles month ends, year ends and February correctly.

## Tests (`tests/test_api.py`)

- `test_seeded_express_order_lookup`: `GET /api/orders/express-1002` must return 200 with
  `estimated_delivery`. Because the seed date is always the last day of a month, this test
  fails on the old code no matter when it runs.
- `test_express_estimated_delivery_crosses_month_end`: a parametrized unit test of
  `order_detail()` covering mid-month, 30 Sep → 2 Oct, 27 Feb → 1 Mar and 31 Dec → 2 Jan.

## Verification

**Status: NOT RUN. The fix has not been deployed, so the incident is still open.**
This session again had no way to approve shell commands. Every Bash or PowerShell call
(`git diff`, `uv run pytest`, and so on) was denied automatically. Run these steps by hand
to close the incident:

```
uv run --frozen pytest -q
docker compose up --build -d --wait
curl -i http://127.0.0.1:8000/api/orders/express-1002
```

Expected results: all tests pass. `curl` returns `HTTP/1.1 200 OK` with
`"estimated_delivery": "2026-10-02"`. (Port 8000 is the default; it can be changed with
`ORDER_TRACKER_PORT`.)

**Follow-up:** Commit the fix after verifying it. Also allow the responder agent to run
`uv run`, `docker compose` and `curl`. Without those permissions, each new alert produces
another report and nothing gets deployed.
