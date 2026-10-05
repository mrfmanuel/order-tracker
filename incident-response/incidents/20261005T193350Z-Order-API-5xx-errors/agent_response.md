I found and fixed the root cause and added tests, but nothing has been run yet. This session couldn't run the tests, the Docker rebuild or the curl check, so steps 5–7 are still yours to do.

**Root cause:** `order_detail()` in `app/main.py:61` worked out the express delivery estimate with `placed_at.replace(day=placed_at.day + 2)`. That doesn't roll over into the next month, so for any express order placed in the last two days of a month it asks for a day that doesn't exist (Sep 30 → day 32). Python raises a `ValueError` and the route returns a 500. The seed order `express-1002` is always created on the last day of the previous month, so every lookup of it fails. That matches the evidence: every error in `logs.txt` is `express-1002 -> 500`, and the traces show errored `get_order` spans.

**Fix:** `estimated_at = placed_at + timedelta(days=2)`, which handles month and year boundaries correctly.

**Tests added** in `tests/test_api.py`:
- `test_express_order_placed_at_month_end`: looking up `express-1002` must return 200 with a delivery estimate 2 days after the order date.
- `test_express_estimated_delivery_crosses_month_boundaries`: checks the date calculation directly for mid-month, Sep 29/30, Feb 28 and Dec 31.

**Report:** written to `report.md` in the incident folder. Its verification section says the checks haven't been run yet, rather than showing any results.

**What was blocked:** every shell command needs approval, and this session has no way to give it. So these didn't run, and you'll need to run them from the repo root:
```
uv run --frozen pytest -q
docker compose up --build -d --wait
curl -i http://localhost:8000/api/orders/express-1002   # adjust port if different
```
Then paste the output into the report's verification section. I couldn't find a published port in the compose file, so check that `8000` is right. I didn't commit anything because I couldn't confirm the tests pass first.
