# ADR-0001: Single Source of Truth

## Status

Accepted

## Date

2026-06-11

## Context

DayZ server administration traditionally relies on multiple independent scripts and configuration files.

Typical examples include:

- Startup scripts
- Update scripts
- Backup scripts
- Mod management scripts
- Key synchronization scripts
- Cron jobs
- Systemd units

Over time these components tend to drift apart.

Common issues include:

- Mods configured in one place but not another
- Startup parameters becoming outdated
- Missing .bikey files after mod updates
- Backups excluding critical data
- Update routines not reflecting current server configuration
- Duplicate configuration values spread across multiple files

As the number of installed mods increases, operational complexity grows significantly.

The project requires a mechanism that guarantees consistency across all operations.

---

## Decision

All server configuration shall be defined in a single declarative configuration file:

```text
/srv/dayz/config/server.yaml
```

This file becomes the authoritative source of truth for the entire platform.

All DayZCTL components must derive their behavior from this configuration.

Examples include:

- Server startup
- Mod installation
- Mod removal
- Key synchronization
- Backup generation
- Update workflows
- Managed file deployment
- Managed directory deployment
- Health checks

No other component may maintain independent configuration state.

Generated state may be stored separately, but must never become authoritative.

Examples:

```text
/srv/dayz/state/installed-mods.yaml
/srv/dayz/state/keys.yaml
/srv/dayz/state/server-state.yaml
```

State files are implementation details and may be regenerated at any time.

---

## Consequences

### Positive

- Centralized configuration
- Predictable operations
- Reduced configuration drift
- Easier troubleshooting
- Simplified automation
- Easier disaster recovery
- Better Git version control
- Infrastructure-as-Code workflow

### Negative

- Requires YAML parsing support
- Increased importance of configuration validation
- Configuration errors can impact multiple subsystems

### Neutral

- Additional generated state files may be created internally
- Some operations may require reconciliation between desired state and actual state

---

## Alternatives Considered

### Multiple Independent Configuration Files

Example:

```text
mods.yaml
backup.yaml
startup.conf
update.conf
```

Rejected because configuration becomes fragmented and difficult to maintain.

### Script-Centric Configuration

Configuration embedded directly inside Bash scripts.

Rejected because operational logic becomes tightly coupled with configuration data.

### Database-Backed Configuration

Store configuration in SQLite or PostgreSQL.

Rejected because it introduces unnecessary complexity for a single-server deployment.

---

## Implementation Notes

The following components must consume configuration exclusively from:

```text
/srv/dayz/config/server.yaml
```

Components:

- dayzctl
- dayz.service
- dayz-update.service
- backup engine
- mod synchronization engine
- key synchronization engine
- managed resource engine

Future components must follow the same principle.

---

## References

Related ADRs:

- ADR-0002: Use Systemd Timers Instead of Cron
- ADR-0003: Symlink-Based Mod Management
- ADR-0004: Full Key Directory Rebuild Strategy
- ADR-0005: Backup and Recovery Strategy
