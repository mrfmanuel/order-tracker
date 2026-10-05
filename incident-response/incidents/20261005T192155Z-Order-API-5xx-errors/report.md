# Incident report: Order API 5xx errors

- **Alert:** Order API 5xx errors (Grafana), started 2026-10-05T19:21:50Z
- **Route:** `GET /api/orders/{order_id}`
- **Evidence:** `logs.txt` shows `[ERROR] order lookup for express-1002 -> 500`. `traces.json` returned no traces.

## Root cause

`order_detail()` in `app/main.py` worked out the estimated delivery date for express orders like this:

```python
estimated_at = placed_at.replace(day=placed_at.day + 2)
```

`datetime.replace(day=...)` doesn't roll over into the next month. For any express order placed in the last two days of a month, this raises `ValueError: day is out of range for month`. The endpoint returns that as a 500.

The seeded order `express-1002` always has `created_at` set to the last day of the previous month (`now.replace(day=1) - timedelta(days=1)`). So every lookup of that order failed, whatever the date.

## Fix

Use date arithmetic, which handles month and year boundaries:

```python
estimated_at = placed_at + timedelta(days=2)
```

## Tests added (`tests/test_api.py`)

- `test_seeded_express_order_lookup`: `GET /api/orders/express-1002` returns 200 with `estimated_delivery`.
- `test_express_estimated_delivery_crosses_month_end`: calls `order_detail` with dates mid-month, at month end (30 Sep), at February end (27 Feb → 1 Mar) and at year end (31 Dec → 2 Jan).

Both tests fail with the old code: the month-end cases raise `ValueError`.

## Verification

**Not done.** This session couldn't run shell commands because they needed approval and nobody could give it. These steps still need to be run:

```
uv run --frozen pytest -q
docker compose up --build -d --wait
curl -i http://localhost:8000/api/orders/express-1002   # expect HTTP 200 with estimated_delivery
```

(Change the port if the app is exposed on a different one in `docker-compose.yml`.)
