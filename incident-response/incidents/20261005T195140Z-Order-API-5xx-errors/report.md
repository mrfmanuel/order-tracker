# Incident report: Order API 5xx errors

- **Alert:** Order API 5xx errors (Grafana). Payload status: `resolved`, window 2026-10-05T19:49:50Z to 19:51:40Z
- **Affected route:** `GET /api/orders/{order_id}`
- **Affected request:** `GET /api/orders/express-1002`

## Evidence
- `logs.txt`: `[ERROR] order lookup for express-1002 -> 500` (x2), followed by
  `express-1002 -> 200` and `standard-1001 -> 200`.
- `traces.json`: `get_order` spans for `order-tracker` on route `/api/orders/{order_id}`.
- Only express orders failed. Standard orders were fine.

## Root cause
`order_detail()` in `app/main.py` estimated express delivery with:

```python
estimated_at = placed_at.replace(day=placed_at.day + 2)
```

`datetime.replace(day=...)` doesn't roll over into the next month. Any express
order placed in the last two days of a month (for example, `express-1002`,
seeded on the last day of the previous month, 2026-09-30) raised
`ValueError: day is out of range for month`. The handler surfaced this as an
HTTP 500.

## Fix
Use date arithmetic instead (`app/main.py:61`):

```python
estimated_at = placed_at + timedelta(days=2)
```

This fix was already committed as `36663b9` ("Fix 500 on express order lookup
at month end") before this run. The alert payload is `resolved`, and the last
log lines show `express-1002 -> 200`, which is consistent with that. No further
code change was needed. This run re-verified the fix.

## Tests
`tests/test_api.py` covers the regression:
- `test_seeded_express_order_lookup`: `GET /api/orders/express-1002` returns 200 with `estimated_delivery`.
- `test_express_estimated_delivery_crosses_month_end`: checks month end (09-30), Jan 31 (crossing into February), the year boundary (12-31) and a mid-month date.

```
$ uv run --frozen pytest -q
.........                                                                [100%]
9 passed, 3 warnings in 2.15s
```

## Verification
`docker compose up --build -d --wait`: all containers healthy (`order-tracker-app-1` recreated and healthy).

```
$ curl http://127.0.0.1:8000/api/orders/express-1002
{"id":"express-1002","customer":"Sam","item":"Headphones","priority":"express","status":"preparing","created_at":"2026-09-30T17:38:42.737874+00:00","estimated_delivery":"2026-10-02"}
HTTP 200

$ curl http://127.0.0.1:8000/api/orders/standard-1001
{"id":"standard-1001","customer":"Avery","item":"Notebook","priority":"standard","status":"received","created_at":"2026-10-05T17:38:42.737874+00:00"}
HTTP 200
```
