# ADR-0004: Full Key Directory Rebuild Strategy

## Status

Accepted

## Date

2026-06-11

## Context

DayZ uses .bikey files to validate client signatures.

Workshop mods place keys in inconsistent locations:

```text
keys/
Keys/
key/
Key/
```

Some mods also change key names during updates.

Incremental synchronization can leave:

- Orphaned keys
- Duplicate keys
- Outdated keys

---

## Decision

dayzops shall rebuild the complete key directory during synchronization.

Process:

1. Remove existing keys
2. Scan all installed mods
3. Discover all .bikey files
4. Remove duplicates
5. Rebuild server keys directory

Recursive search:

```bash
find MOD_PATH -type f -iname "*.bikey"
```

---

## Consequences

### Positive

- Predictable state
- No orphaned keys
- No stale keys
- Simplified logic

### Negative

- Slightly slower synchronization

---

## Alternatives Considered

### Incremental Updates

Rejected due to complexity and drift risk.

---

## References

Related ADRs:

- ADR-0001: Single Source of Truth
- ADR-0003: Symlink-Based Mod Management
