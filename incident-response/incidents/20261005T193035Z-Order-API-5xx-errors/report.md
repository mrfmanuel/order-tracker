# Incident report: Order API 5xx errors

- **Alert:** Grafana "Order API 5xx errors"
- **Route:** `/api/orders/{order_id}`
- **Detected:** 2026-10-05T19:30:35Z

## Evidence

- `logs.txt`: every failing request is the same order:
  `[ERROR] order lookup for express-1002 -> 500` (6 times).
- `traces.json`: 6 `get_order` traces from `order-tracker` on `/api/orders/{order_id}`,
  each with `errorCount: 1`. The trace search results don't include the exception attributes.

## Root cause

`app/main.py`, `order_detail()` worked out the express delivery estimate with:

```python
estimated_at = placed_at.replace(day=placed_at.day + 2)
```

`datetime.replace()` does not roll over into the next month. It raises
`ValueError: day is out of range for month` when the new day number is past the end of
the month. That happens for any express order placed in the last two days of a month
(or the last day of February).

The seeded order `express-1002` is created on the last day of the previous month
(`now.replace(day=1) - timedelta(days=1)`, which is 2026-09-30 today). The code tried to
build Sept 32. `get_order` caught the error as a generic exception and returned HTTP 500,
which triggered the alert. Standard orders skip this code, so only express orders were
affected.

## Fix

Use date arithmetic instead of changing the day field directly:

```python
estimated_at = placed_at + timedelta(days=2)
```

`timedelta` was already imported. This correctly handles month ends, year ends and
February.

## Tests added (`tests/test_api.py`)

- `test_seeded_express_order_lookup`: `GET /api/orders/express-1002` must return 200 with
  `estimated_delivery`. This is the request that was failing. Because the seed date is
  always the last day of the previous month, this test would have failed before the fix
  every time it ran.
- `test_express_estimated_delivery_crosses_month_end`: a parametrized unit test of
  `order_detail()` covering a mid-month date, 30 Sep → 2 Oct, 27 Feb → 1 Mar and
  31 Dec → 2 Jan (next year).

## Verification

**Status: NOT YET RUN.** In the session that wrote this report, every shell command needed
approval and none could be given, so these steps were not run:

1. `uv run --frozen pytest -q`
2. `docker compose up --build -d --wait`
3. `curl -i http://localhost:<app-port>/api/orders/express-1002` (expect `200` with
   `"estimated_delivery": "2026-10-02"`)

Paste the output of these commands here once they have been run.
