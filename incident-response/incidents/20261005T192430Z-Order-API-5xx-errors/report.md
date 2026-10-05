# Incident report: Order API 5xx errors

- **Alert:** Grafana "Order API 5xx errors"
- **Route:** `GET /api/orders/{order_id}`
- **Incident folder:** `20261005T192430Z-Order-API-5xx-errors`

## Evidence

- `logs.txt`: repeated `[ERROR] order lookup for express-1002 -> 500`.
- `traces.json`: four `get_order` traces on `/api/orders/{order_id}`, each with `errorCount: 1`.
- Only the express order failed. Standard orders were unaffected.

## Root cause

`app/main.py`, `order_detail()` worked out the express delivery estimate like this:

```python
estimated_at = placed_at.replace(day=placed_at.day + 2)
```

`datetime.replace(day=...)` doesn't roll over into the next month. It raises
`ValueError: day is out of range for month` when `day + 2` is past the end of the month.
So any express order placed in the last two days of a month caused an unhandled
exception and a 500 response.

The seed data puts `express-1002` on the **last day of the previous month**, so that order failed every time.

## Fix

Use date arithmetic, which rolls over months and years correctly:

```python
estimated_at = placed_at + timedelta(days=2)
```

## Tests added (`tests/test_api.py`)

- `test_seeded_express_order_lookup`: `GET /api/orders/express-1002` returns 200 and includes `estimated_delivery`.
- `test_express_estimated_delivery_crosses_month_end`: checks `order_detail` with dates in the middle of a month, at the end of a month (Sep 30), at the end of February, and at the end of the year (Dec 31 → Jan 2).

Either test would have caught this bug.

## Verification

**Not done.** This agent session had no way to approve commands, so these steps were
blocked and must be run by hand:

```
uv run --frozen pytest -q
docker compose up --build -d --wait
curl -i http://localhost:8000/api/orders/express-1002   # expect HTTP 200 with estimated_delivery
```

(Adjust the host/port to match `docker-compose.yml`.)

The fix and the tests have been reviewed but **not executed** in this session.
