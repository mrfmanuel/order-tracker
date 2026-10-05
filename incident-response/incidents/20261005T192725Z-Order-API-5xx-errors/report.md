# Incident report: Order API 5xx errors

- **Alert:** Grafana "Order API 5xx errors"
- **Affected route:** `GET /api/orders/{order_id}`
- **Date:** 2026-10-05

## Evidence

- `logs.txt`: repeated `[ERROR] order lookup for express-1002 -> 500`. Only this one order fails.
- `traces.json`: 4 `get_order` traces on `/api/orders/{order_id}`, each with `errorCount: 1`.
- Only **express** orders go through extra processing (`order_detail` computes `estimated_delivery`).

## Root cause

`app/main.py`, `order_detail()` computed the express delivery estimate as:

```python
estimated_at = placed_at.replace(day=placed_at.day + 2)
```

`datetime.replace(day=...)` does not roll over into the next month. It raises
`ValueError: day is out of range for month` for any express order placed in the
last two days of a month. The seeded order `express-1002` is created on the
last day of the previous month (2026-09-30), so `replace(day=32)` fails. The
exception escapes `get_order`, which records it and returns 500 on every lookup.

## Fix

Use date arithmetic, which handles month and year boundaries correctly:

```python
estimated_at = placed_at + timedelta(days=2)
```

## Tests added (`tests/test_api.py`)

- `test_seeded_express_order_lookup`: `GET /api/orders/express-1002` returns 200
  and includes `estimated_delivery` (this is the exact request that was failing).
- `test_express_estimated_delivery_crosses_month_end`: parametrized cases for
  mid-month, the end of a 30-day month, the end of February, and the end of the year.

## Verification

**Not yet performed.** In this automated session, running commands needed
approval that couldn't be given, so none of these ran:

- `uv run --frozen pytest -q`
- `docker compose up --build -d --wait`
- `curl -i http://localhost:8000/api/orders/express-1002`

To finish the verification, run those commands by hand and confirm that the
curl returns `HTTP/1.1 200` with an `estimated_delivery` field. Also check that
the 5xx alert resolves in Grafana.
