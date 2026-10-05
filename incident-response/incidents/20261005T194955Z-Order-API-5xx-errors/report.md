# Incident report: Order API 5xx errors

- **Alert:** Grafana "Order API 5xx errors"
- **Affected route:** `GET /api/orders/{order_id}`
- **Evidence:** `logs.txt` shows `[ERROR] order lookup for express-1002 -> 500` (repeated)

## Root cause

`order_detail()` in `app/main.py` computed the estimated delivery date for express
orders as:

```python
estimated_at = placed_at.replace(day=placed_at.day + 2)
```

`datetime.replace()` does not roll over into the next month. Order `express-1002` was
created on the last day of the previous month (`2026-09-30`), so this asked for
September 32. That raised `ValueError: day is out of range for month`, and the request
returned a 500. Any express order placed in the last two days of a month would fail
the same way. Standard orders were not affected because they skip this code path.

## Fix

Use date arithmetic, which rolls over months and years correctly:

```python
estimated_at = placed_at + timedelta(days=2)
```

## Tests added (`tests/test_api.py`)

- `test_seeded_express_order_lookup`: `GET /api/orders/express-1002` returns 200 with
  `estimated_delivery`.
- `test_express_estimated_delivery_crosses_month_end`: parametrized over Sep 30,
  Jan 31, Dec 31 (year rollover) and a mid-month date.

## Verification

`uv run --frozen pytest -q`:

```
9 passed, 3 warnings in 2.11s
```

`docker compose up --build -d --wait`: image rebuilt and all containers healthy.

```
$ curl http://127.0.0.1:8000/api/orders/express-1002
{"id":"express-1002","customer":"Sam","item":"Headphones","priority":"express","status":"preparing","created_at":"2026-09-30T17:38:42.737874+00:00","estimated_delivery":"2026-10-02"}
HTTP 200

$ curl http://127.0.0.1:8000/api/orders/standard-1001
{"id":"standard-1001","customer":"Avery","item":"Notebook","priority":"standard","status":"received","created_at":"2026-10-05T17:38:42.737874+00:00"}
HTTP 200
```
