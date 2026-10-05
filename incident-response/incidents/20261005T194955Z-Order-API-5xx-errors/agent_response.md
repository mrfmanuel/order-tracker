I fixed the bug, and `GET /api/orders/express-1002` now returns 200 instead of 500.

**Root cause:** In `app/main.py:61`, the delivery estimate for express orders was calculated with `placed_at.replace(day=placed_at.day + 2)`. That method doesn't roll over into the next month. Order `express-1002` was placed on 2026-09-30, so the code asked for September 32, which raised a `ValueError` and returned a 500. Any express order placed in the last two days of a month would fail the same way.

**Fix:** The line is now `placed_at + timedelta(days=2)`, which handles month and year boundaries correctly.

**Test:** I added two tests in `tests/test_api.py`:
- One requests the `express-1002` order through the API and expects a 200.
- One checks the delivery date for orders placed on Sep 30, Jan 31, Dec 31 (crossing into the next year) and a mid-month date.

**Verification:**
- `uv run --frozen pytest -q`: 9 passed.
- `docker compose up --build -d --wait`: the image rebuilt and every container reported healthy.
- `curl http://127.0.0.1:8000/api/orders/express-1002` returned HTTP 200 with `"estimated_delivery":"2026-10-02"`. A standard order also still returns 200.

**Report:** written to `incident-response/incidents/20261005T194955Z-Order-API-5xx-errors/report.md`.

I committed the fix and the tests as `36663b9`. The report and incident folders are not committed, and nothing was pushed.

One thing was blocked: my first command to read the evidence files was denied because this session can't approve permission prompts. I read the files with the file viewer instead, so nothing was missed.
