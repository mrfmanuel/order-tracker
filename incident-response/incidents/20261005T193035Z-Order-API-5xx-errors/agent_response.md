I found and fixed the root cause, but none of the fix has been tested or run. Every shell command needed approval and this session couldn't ask for it, so tests, the rebuild, the curl check and the commit didn't happen.

**Root cause:** In `app/main.py:61`, `order_detail()` worked out the express delivery date with `placed_at.replace(day=placed_at.day + 2)`. That fails with `ValueError: day is out of range for month` for any express order placed in the last two days of a month. The seeded order `express-1002` is always dated the last day of the previous month (2026-09-30 today), so the code tried to build Sept 32 and the request returned a 500. That matches the evidence: all 6 log lines are `order lookup for express-1002 -> 500`, and each of the 6 traces has `errorCount: 1`.

**Fix:** The working tree already had the change when I started, probably from an earlier run. The line is now `estimated_at = placed_at + timedelta(days=2)`. I checked that this is correct and complete; `timedelta` was already imported.

**Tests:** Also already in `tests/test_api.py`:
- `test_seeded_express_order_lookup` requests `express-1002` and expects a 200. It would have failed before the fix every time.
- `test_express_estimated_delivery_crosses_month_end` checks the date across month ends, February and year end.

**Report:** Written to `incident-response/incidents/20261005T193035Z-Order-API-5xx-errors/report.md`. Its verification section is marked "NOT YET RUN".

To finish, please run:
```
uv run --frozen pytest -q
docker compose up --build -d --wait
curl -i http://localhost:<port>/api/orders/express-1002   # expect 200, "estimated_delivery": "2026-10-02"
```
Then paste the output into the report. You can also commit `app/main.py` and `tests/test_api.py`, or give approval and I'll run these steps and commit.
