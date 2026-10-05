I found the root cause and the fix is in place. But I couldn't run the tests, rebuild the stack, or curl the endpoint. This session can't approve commands, so `uv run`, `docker compose` and `curl` were all blocked. Nothing is verified yet.

**Root cause** (`app/main.py:61`): express orders got their delivery date from `placed_at.replace(day=placed_at.day + 2)`. That raises `ValueError` for any express order placed in the last two days of a month, because the day goes past the end of the month. The seeded order `express-1002` was placed on 2026-09-30, so the code tried day 32 and every lookup of it returned 500. That matches the logs (only `express-1002 -> 500`) and the 4 failed traces.

**Fix:** `estimated_at = placed_at + timedelta(days=2)`, which rolls over into the next month and year correctly. This change was already uncommitted in your working tree, apparently from an earlier responder run on the same alert. I checked it and made no further code changes.

**Tests** (`tests/test_api.py`), also already uncommitted in the working tree:
- `test_seeded_express_order_lookup` sends the exact request that was failing and expects a 200 with `estimated_delivery`.
- `test_express_estimated_delivery_crosses_month_end` checks four dates: mid-month, the end of a 30-day month, the end of February, and the end of the year.

**Report:** I wrote `incident-response/incidents/20261005T192725Z-Order-API-5xx-errors/report.md`. Its Verification section says verification is still pending, rather than showing output that never ran.

**To finish, run these yourself:**
```
uv run --frozen pytest -q
docker compose up --build -d --wait
curl -i http://localhost:8000/api/orders/express-1002
```
The curl should return HTTP 200 with an `estimated_delivery` field. Port 8000 is the default `ORDER_TRACKER_PORT` in `compose.yaml`. Once those pass, add the output to the report. You can also commit `app/main.py` and `tests/test_api.py`; I didn't commit anything.
