
# ADR-0010: State Inventory Management

## Status

Accepted

## Date

2026-06-11

## Context

The platform requires operational visibility.

Questions administrators should be able to answer:

- Which mods are installed?
- Which keys are active?
- When was the last backup?
- When was the last update?
- What changed since yesterday?

Relying solely on filesystem inspection is inefficient.

---

## Decision

DayZCTL shall maintain generated state inventories.

Location:

```text
/srv/dayz/state
```

Files:

```text
installed-mods.json
installed-keys.json
last-backup.json
last-update.json
inventory.json
```

These files are generated automatically.

They must never be manually edited.

---

## Consequences

### Positive

- Improved observability
- Easier troubleshooting
- Faster validation

### Negative

- Additional generated metadata

---

## Alternatives Considered

### Filesystem Scanning Only

Rejected due to slower operations and limited visibility.

---

## References

Related ADRs:

- ADR-0001: Single Source of Truth
