The fix for this alert was already in the code before I started, so I didn't change any code. I ran the tests, rebuilt the stack, confirmed the failing request now works, and wrote the report.

**Root cause:** For express orders, `app/main.py` estimated delivery with `placed_at.replace(day=placed_at.day + 2)`. That fails for orders placed in the last two days of a month, because the day number goes past the end of the month. The seeded order `express-1002` is dated 2026-09-30, so looking it up returned a 500.

**Fix:** Commit `36663b9` changes it to `placed_at + timedelta(days=2)` (`app/main.py:61`), which rolls over into the next month. That commit also added the tests that catch this in `tests/test_api.py`:
- `test_seeded_express_order_lookup` requests `express-1002` and expects a 200.
- `test_express_estimated_delivery_crosses_month_end` checks Sept 30, Jan 31, Dec 31 and a mid-month date.

The alert payload is already `resolved`, and the last log lines show `express-1002 -> 200`, which fits that commit having been deployed.

**Verification:**
- **Tests:** `uv run --frozen pytest -q` gave 9 passed.
- **Stack:** `docker compose up --build -d --wait` recreated the app container, and every container reported healthy.
- **Request:** `curl http://127.0.0.1:8000/api/orders/express-1002` returned HTTP 200 with `"estimated_delivery":"2026-10-02"`. `standard-1001` also returned 200.

**Report:** written to `incident-response/incidents/20261005T195140Z-Order-API-5xx-errors/report.md`.

**Blocked:** I couldn't run `git status` or `git show HEAD` because this session can't answer permission prompts. I confirmed the fix from the current source and from `first-attempt-fix.patch` instead. Nothing was committed, since there were no code changes.
