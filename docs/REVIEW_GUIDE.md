# Code Review Guide

This guide helps a reviewer evaluate the project without reading the entire application.

## 15-minute path

1. Read the trust-boundary section in the root README.
2. Inspect `backend/app/agent.py` and locate the bounded tool loop.
3. Inspect `backend/app/tools.py` and follow slot lookup into booking creation.
4. Review the PostgreSQL constraints in `backend/app/db.py` and the matching migrations.
5. Read the focused tests in `backend/tests/test_tools.py`, `test_agent.py`, `test_security.py`, and `test_notifications.py`.

## Questions the code is intended to answer

- How is an LLM prevented from fabricating a booking?
- How does the system prevent two concurrent requests from taking the same interval?
- What happens if the external calendar fails after the customer confirms?
- How are duplicate webhooks and notification retries handled?
- Where is tenant isolation enforced?
- Which failures become human handoffs instead of model guesses?
- How does the deployment avoid concurrent schema migrations?

## Verification

Run:

```bash
DB_ALLOW_SQLITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  python -m pytest backend/tests -q
```

The CI workflow runs the same command on Python 3.12.

