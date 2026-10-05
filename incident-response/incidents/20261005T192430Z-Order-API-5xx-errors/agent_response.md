I found the root cause and the fix and wrote the report, but nothing has been run or verified. This session can't approve commands, so the test run, the stack rebuild and the curl check were all blocked.

**Root cause:** In `app/main.py:61`, `order_detail()` worked out the express delivery date with `placed_at.replace(day=placed_at.day + 2)`. That crashes for any express order placed in the last two days of a month, because there is no day 32 or 33. The seed data puts `express-1002` on the last day of the previous month, which explains the repeated `express-1002 -> 500` lines in `logs.txt` and the errors in all four traces.

**Fix and tests:** These were already uncommitted in your working tree, probably from an earlier run on one of the duplicate incident folders. I checked them with `git diff` and they look right, so I didn't change anything:
- The fix changes the line to `placed_at + timedelta(days=2)`, which rolls over into the next month and year correctly.
- Two new tests in `tests/test_api.py`:
  - one requests `express-1002` and expects a 200;
  - the other checks the delivery date for orders placed mid-month, at the end of September, at the end of February and on December 31.

Either test would have caught this.

**Blocked:** I also couldn't run plain `git diff` through Bash; it worked in PowerShell. Please run these yourself:
```
uv run --frozen pytest -q
docker compose up --build -d --wait
curl -i http://localhost:8000/api/orders/express-1002
```
The curl should return 200 with an `estimated_delivery` field. Adjust the port if your compose file uses a different one.

**Report:** Written to `incident-response/incidents/20261005T192430Z-Order-API-5xx-errors/report.md`. It covers the root cause and the fix, and says plainly that verification hasn't happened. Paste in the test and curl output once you have it.

Nothing is committed yet. If you'd like a commit, allow git commands and I'll make one.
