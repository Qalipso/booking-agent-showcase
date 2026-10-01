# Backend

The backend is a multi-tenant FastAPI application backed by SQLAlchemy and PostgreSQL. It owns booking rules, agent tools, calendar synchronization, authentication, notification scheduling, and administration APIs.

For setup, architecture, verified test status, and a review path, see the [repository README](../README.md).

## Module map

| Module | Responsibility |
| --- | --- |
| `app/agent.py` | Model-provider abstraction and bounded tool loop |
| `app/tools.py` | Deterministic slot, booking, cancellation, and handoff operations |
| `app/db.py` | Models, tenant-scoped persistence, constraints, and queue storage |
| `app/calendar_service.py` | Google Calendar availability and event synchronization |
| `app/notify/` | Notification templates, providers, scheduling, retries, and fallback |
| `app/policies.py` | Slot signatures, rate limits, confirmations, and PII masking |
| `app/secretstore.py` | Environment- and database-backed secret resolution |
| `app/routers/` | Public, administrative, CRM, messaging, and staff APIs |
| `migrations/` | Alembic migration history |
| `tests/` | Unit, API, integration-boundary, migration, and security tests |

