I found and fixed the root cause and added tests. But I couldn't run anything: no tests, no rebuild, no curl check. Every shell command needs approval, and this session can't grant it, so they were all blocked.

**Root cause:** The only useful evidence was in `logs.txt`: `order lookup for express-1002 -> 500`. `traces.json` was empty. In `app/main.py`, `order_detail()` worked out an express order's delivery date with `placed_at.replace(day=placed_at.day + 2)`. That crashes with `ValueError: day is out of range for month` for any express order placed in the last two days of a month, and the endpoint returns it as a 500. The seeded order `express-1002` is always dated the last day of the previous month, so every lookup of it fails.

**Fix:** In `app/main.py:61`, it is now `estimated_at = placed_at + timedelta(days=2)`, which carries over correctly into the next month and year.

**Tests added in `tests/test_api.py`:**
- `test_seeded_express_order_lookup` checks that `GET /api/orders/express-1002` returns 200 with `estimated_delivery`.
- `test_express_estimated_delivery_crosses_month_end` checks dates mid-month, at month end, at the end of February and at year end.

Both should fail on the old code and pass with the fix, but I haven't run them.

**Report:** written to `incident-response/incidents/20261005T192155Z-Order-API-5xx-errors/report.md`. It covers the root cause and the fix, and says plainly that verification hasn't been done yet.

**To finish, run these from the repo root:**
```
uv run --frozen pytest -q
docker compose up --build -d --wait
curl -i http://localhost:8000/api/orders/express-1002
```
I couldn't find the app's port in the compose file, so `8000` is a guess. Once the request returns 200, paste the output into the report's Verification section. I haven't committed anything.
