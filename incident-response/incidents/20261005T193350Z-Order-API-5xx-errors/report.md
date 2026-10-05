# Incident report: Order API 5xx errors (`/api/orders/{order_id}`)

- Alert: `Order API 5xx errors`. Started 2026-10-05T19:32:10Z. The payload received at 19:33:50Z already shows the alert as resolved because the error window aged out.
- Service: `order-tracker`
- Affected route: `/api/orders/{order_id}`

## Evidence

- `logs.txt`: every error line reads `[ERROR] order lookup for express-1002 -> 500`.
- `traces.json`: the `get_order` spans for `/api/orders/{order_id}` show `errorCount: 1`.
- Other orders (`standard-1001`, `standard-1003`) and unknown IDs (404) were not affected. Only express orders failed.

## Root cause

`order_detail()` in `app/main.py` worked out the estimated delivery date for express orders like this:

```python
estimated_at = placed_at.replace(day=placed_at.day + 2)
```

`datetime.replace(day=...)` doesn't roll over into the next month. Any express order placed in the last two days of a month asks for a day that doesn't exist (e.g. Sep 30 → day 32). That raises `ValueError: day is out of range for month`, which the route turns into a 500.

The seed data creates `express-1002` on the last day of the previous month (`now.replace(day=1) - timedelta(days=1)`). That means every lookup of this order fails, no matter when it runs.

## Fix

Use date arithmetic, which rolls over month and year boundaries correctly:

```python
estimated_at = placed_at + timedelta(days=2)
```

## Test coverage added (`tests/test_api.py`)

- `test_express_order_placed_at_month_end`: `GET /api/orders/express-1002` (the seeded month-end order) must return 200 with an `estimated_delivery` 2 days after `created_at`.
- `test_express_estimated_delivery_crosses_month_boundaries`: a parametrized unit test of `order_detail` covering mid-month, Sep 29/30 → October, Feb 28 → March, and Dec 31 → next year.

## Verification

**Not yet performed.** The session that wrote this fix could not run shell commands because there was no way to approve them. Run these steps and paste the output here:

1. `uv run --frozen pytest -q`: all tests should pass.
2. `docker compose up --build -d --wait`
3. `curl -i http://localhost:8000/api/orders/express-1002`: should return `HTTP/1.1 200 OK` with an `estimated_delivery` field. Adjust the port to match `docker-compose.yml`.
