# ADR-0002: Use Systemd Timers Instead of Cron

## Status

Accepted

## Date

2026-06-11

## Context

DayZ servers require scheduled maintenance tasks:

- Server updates
- Mod updates
- Backup creation
- Cleanup operations

Historically these tasks are executed through cron jobs.

Cron provides simple scheduling but lacks integration with service management and operational visibility.

The project requires:

- Centralized logging
- Failure visibility
- Dependency management
- Native Linux service integration

---

## Decision

DayZCTL shall use systemd timers instead of cron.

Scheduled operations will be executed through:

- dayz-update.service
- dayz-update.timer

Additional scheduled services may be introduced in the future.

---

## Consequences

### Positive

- Native systemd integration
- Journal logging
- Service dependency support
- Better operational visibility
- Easier troubleshooting

### Negative

- Requires systemd
- Slightly more complex configuration

---

## Alternatives Considered

### Cron

Rejected due to limited visibility and lack of service integration.

### Custom Scheduler

Rejected due to unnecessary complexity.

---

## References

Related ADRs:

- ADR-0001: Single Source of Truth
