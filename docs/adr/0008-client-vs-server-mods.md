
# ADR-0008: Client vs Server Mods

## Status

Accepted

## Date

2026-06-11

## Context

DayZ supports two distinct categories of modifications.

Client Mods:

- Required by connecting players
- Loaded through -mod

Server Mods:

- Loaded only by the server
- Loaded through -serverMod

Mixing both categories creates operational confusion.

---

## Decision

Configuration shall explicitly separate both categories.

Example:

```yaml
mods:
  - id: 1559212036

servermods:
  - id: 1234567890
```

Generated startup parameters:

```text
-mod=
-serverMod=
```

Each category shall be synchronized independently.

---

## Consequences

### Positive

- Clear separation of responsibilities
- Easier troubleshooting
- Cleaner startup generation

### Negative

- Additional configuration structure

---

## Alternatives Considered

### Single Mod List

Rejected because DayZ treats both categories differently.

---

## References

Related ADRs:

- ADR-0001: Single Source of Truth
