
# ADR-0007: Mod Order Generation

## Status

Accepted

## Date

2026-06-11

## Context

DayZ mod loading order directly affects server startup and runtime behavior.

Many mods require framework mods to load first.

Examples:

- CF
- Dabs Framework
- Community Online Tools
- Expansion Core

Incorrect ordering may cause:

- Startup failures
- Missing functionality
- Script conflicts

---

## Decision

Mod loading order shall be determined exclusively by the order declared in server.yaml.

Example:

```yaml
mods:
  - id: 1559212036
  - id: 2545327648
  - id: 2792982069
```

Generated startup parameters shall preserve the exact order.

dayzops shall not attempt automatic dependency resolution.

Responsibility for ordering remains with the administrator.

---

## Consequences

### Positive

- Predictable behavior
- Simpler implementation
- No dependency guessing

### Negative

- Administrator must understand mod dependencies

---

## Alternatives Considered

### Automatic Dependency Resolution

Rejected due to inconsistent Workshop metadata and increased complexity.

---

## References

Related ADRs:

- ADR-0001: Single Source of Truth
- ADR-0003: Symlink-Based Mod Management
