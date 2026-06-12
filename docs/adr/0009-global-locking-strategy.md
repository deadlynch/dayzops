
# ADR-0009: Global Locking Strategy

## Status

Accepted

## Date

2026-06-11

## Context

Multiple operations may be executed concurrently.

Examples:

- Update
- Backup
- Rollback
- Mod synchronization
- Key synchronization

Concurrent execution can corrupt state.

Examples:

```text
Update running
Backup starts
Update removes files
Backup captures incomplete state
```

---

## Decision

dayzops shall implement a global lock mechanism.

Lock file:

```text
/run/dayzops.lock
```

Operations requiring exclusive access:

- update
- backup
- rollback
- sync-mods
- sync-keys

If lock exists:

```text
Operation aborted
```

Only one critical operation may execute at a time.

---

## Consequences

### Positive

- Prevents race conditions
- Predictable behavior
- Simpler implementation

### Negative

- Operations become serialized

---

## Alternatives Considered

### Per-Operation Locks

Rejected due to increased complexity.

### No Locking

Rejected due to corruption risk.

---

## References

Related ADRs:

- ADR-0006: Atomic Update Workflow
