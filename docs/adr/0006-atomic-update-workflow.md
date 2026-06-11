# ADR-0006: Atomic Update Workflow

## Status

Accepted

## Date

2026-06-11

## Context

Server and mod updates introduce operational risk.

Potential failures include:

- Corrupted downloads
- Incomplete Workshop updates
- Missing dependencies
- Invalid startup parameters
- Missing keys
- SteamCMD failures

A failed update must not leave the server in an unusable state.

---

## Decision

All update operations shall follow an atomic workflow.

Workflow:

```text
Acquire Lock
      │
      ▼
Create Backup
      │
      ▼
Stop Server
      │
      ▼
Update Server
      │
      ▼
Update Mods
      │
      ▼
Validate
      │
      ▼
Sync Keys
      │
      ▼
Start Server
      │
      ▼
Health Check
      │
      ▼
Success
```

If validation fails:

```text
Restore Backup
      │
      ▼
Start Previous Version
```

---

## Consequences

### Positive

- Safe updates
- Fast recovery
- Reduced downtime
- Predictable behavior

### Negative

- Longer update duration
- Additional storage requirements

---

## Alternatives Considered

### In-Place Updates

Rejected due to increased risk of unrecoverable failures.

---

## References

Related ADRs:

- ADR-0001: Single Source of Truth
- ADR-0005: Backup and Recovery Strategy
