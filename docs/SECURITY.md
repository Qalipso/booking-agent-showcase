# Security and Reliability

## Trust boundaries

- The LLM has no database or provider credentials and cannot execute arbitrary operations.
- Tool inputs are validated again by deterministic code.
- Administrative endpoints require a session or machine token.
- Tenant secrets are resolved from environment variables or a database-backed secret store and are never returned to the browser.

## Controls represented in this snapshot

- HMAC-signed slot offers bound to tenant, service, staff member, and time.
- Explicit customer confirmation before booking.
- Constant-time comparison for machine credentials.
- Password hashing and hashed session tokens.
- Tenant-scoped queries and configuration.
- Rate limiting and daily booking limits.
- PII masking in logs and configurable retention.
- CORS allowlists with an explicit development override.
- Provider webhook signature validation where supported.
- Database constraints for duplicate and overlapping bookings.
- Idempotency keys for booking and notification operations.
- Human escalation on calendar errors, unknown intent, or exhausted agent steps.

## Secret and privacy review

The showcase contains placeholder values only. Before publishing any derivative repository, scan both the working tree and Git history, verify that all media is licensed, and confirm that no client-specific information remains.

## Remaining production considerations

- Use a shared rate-limit store when running multiple API replicas.
- Keep provider credentials in the deployment platform's secret manager.
- Rotate secrets after any suspected disclosure; deleting them from the latest commit is not sufficient.
- Run backup restoration checks, not only backup creation checks.
- Add infrastructure-specific monitoring and alerting outside this application repository.

