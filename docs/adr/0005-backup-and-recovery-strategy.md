# ADR-0005: Backup and Recovery Strategy

## Status

Accepted

## Date

2026-06-11

## Context

DayZ servers contain critical persistent data.

Loss of data may result in:

- Lost player progress
- Lost bases
- Lost vehicles
- Lost economy state
- Lost mod configuration

The platform requires reliable disaster recovery.

---

## Decision

DayZCTL shall provide automated backup and rollback functionality.

Default backup scope:

```text
profiles/
mpmissions/
battleye/
config/
custom/
serverDZ.cfg
```

Special attention:

```text
mpmissions/dayzOffline.chernarusplus/storage_1/
```

which contains world persistence.

Backups shall be generated before:

- Server updates
- Mod updates
- Rollback operations

---

## Consequences

### Positive

- Disaster recovery
- Safe updates
- Safe experimentation
- Reduced downtime

### Negative

- Additional storage requirements
- Backup management overhead

---

## Alternatives Considered

### Manual Backups

Rejected due to operational risk.

### Full Filesystem Snapshots Only

Rejected because not all environments support snapshots.

---

## References

Related ADRs:

- ADR-0001: Single Source of Truth
