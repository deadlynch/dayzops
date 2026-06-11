# ADR-0003: Symlink-Based Mod Management

## Status

Accepted

## Date

2026-06-11

## Context

DayZ Workshop mods are downloaded into Workshop directories.

A common approach is copying mod directories into the server installation.

Problems:

- Wasted disk space
- Longer update times
- Duplicate files
- Increased maintenance effort

---

## Decision

DayZCTL shall use symbolic links for mod deployment.

Workshop content remains in:

```text
/srv/dayz/workshop
```

Server-facing mod directories are created as symlinks.

Example:

```text
workshop/1559212036
        │
        ▼
server/@CF
```

---

## Consequences

### Positive

- Reduced storage consumption
- Faster updates
- Single source for mod content
- Simplified maintenance

### Negative

- Symlink validation required
- Additional filesystem checks

---

## Alternatives Considered

### Copy Mods

Rejected due to duplication and update overhead.

### Bind Mounts

Rejected due to operational complexity.

---

## References

Related ADRs:

- ADR-0001: Single Source of Truth
