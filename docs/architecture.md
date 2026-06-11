# Architecture

## Overview

DayZCTL is a declarative management platform for Linux-hosted DayZ servers.

The project centralizes server lifecycle management into a single control plane, eliminating the need for multiple disconnected scripts.

Core responsibilities:

- DayZ Server installation
- Workshop mod management
- Key synchronization (.bikey)
- Server updates
- Mod updates
- Backup and restore
- Rollback
- Health checks
- Resource synchronization
- State management

---

## Design Principles

### Single Source of Truth

All server state is defined in:

```text
/srv/dayz/config/server.yaml
```

No other component should maintain independent state.

### Declarative Configuration

Administrators declare desired state.

DayZCTL is responsible for reconciling the actual state.

### Idempotent Operations

All operations should be safe to execute multiple times.

### Linux Native

The platform is designed specifically for Linux environments using:

- systemd
- SteamCMD
- symlinks
- journald

---

## High-Level Architecture

```text
server.yaml
      │
      ▼
   dayzctl
      │
 ┌────┼────┐
 ▼    ▼    ▼
mods keys backups
      │
      ▼
 dayz.service
      │
      ▼
 DayZ Server
```

---

## Directory Structure

```text
/srv/dayz
├── backups/
├── bin/
│   └── dayzctl
├── config/
│   └── server.yaml
├── custom/
├── logs/
├── runtime/
├── server/
├── state/
└── workshop/
```

### backups

Contains backup archives.

### bin

Executable utilities.

### config

Configuration files.

### custom

User-managed resources.

### logs

Application logs.

### runtime

Lock files and runtime state.

### server

DayZ dedicated server installation.

### state

Generated metadata and inventories.

### workshop

Steam Workshop content.

---

## Configuration Model

The entire environment is described in:

```yaml
server:
  name: "My DayZ Server"

steam:
  username: "steamuser"

mods: []

servermods: []

backup:
  retention_days: 14

logs:
  retention_days: 30

managed_files: []

managed_dirs: []
```

---

## Startup Workflow

```text
validate configuration
        │
        ▼
acquire lock
        │
        ▼
sync mods
        │
        ▼
sync keys
        │
        ▼
generate mod parameters
        │
        ▼
health checks
        │
        ▼
start DayZ server
        │
        ▼
release lock
```

---

## Update Workflow

```text
acquire lock
        │
        ▼
create backup
        │
        ▼
stop server
        │
        ▼
update DayZ
        │
        ▼
update mods
        │
        ▼
validate
        │
        ▼
sync keys
        │
        ▼
cleanup
        │
        ▼
start server
        │
        ▼
release lock
```

---

## Mod Management

Mods are defined in configuration.

Example:

```yaml
mods:
  - id: 1559212036
  - id: 2545327648
```

The synchronization process is responsible for:

- Downloading missing mods
- Updating installed mods
- Removing obsolete mods
- Creating symlinks
- Generating startup parameters

---

## Key Management

DayZCTL never assumes a fixed key directory structure.

The platform performs recursive discovery:

```text
*.bikey
```

within every installed mod.

### Synchronization Strategy

1. Remove all existing keys
2. Discover all available keys
3. Remove duplicates
4. Rebuild key directory

This guarantees consistency.

---

## Backup Strategy

The following resources are considered critical:

```text
profiles/
mpmissions/
serverDZ.cfg
battleye/
config/
custom/
```

### Persistence

Special attention is given to:

```text
mpmissions/dayzOffline.chernarusplus/storage_1/
```

which contains world persistence.

---

## Managed Resources

DayZCTL supports declarative file deployment.

Example:

```yaml
managed_files:
  - source: custom/types.xml
    target: mpmissions/dayzOffline.chernarusplus/db/types.xml
```

Example:

```yaml
managed_dirs:
  - source: custom/expansion_ce
    target: mpmissions/dayzOffline.chernarusplus/expansion_ce
```

---

## State Management

Generated metadata is stored under:

```text
/srv/dayz/state
```

Examples:

```text
installed-mods.yaml
keys.yaml
last-backup.yaml
server-state.yaml
```

State files are generated automatically.

They must not be edited manually.

---

## Locking

To prevent concurrent operations:

```text
/run/dayzctl.lock
```

is created during critical workflows.

Examples:

- update
- backup
- sync-mods
- rollback

---

## Logging

Application logs:

```text
/srv/dayz/logs
```

System logs:

```text
journalctl
```

Retention is configurable.

---

## Health Checks

Validation includes:

- Process running
- Required files exist
- Mod list generated
- Keys synchronized
- Port available
- Startup successful

---

## Future Enhancements

### Phase 2

- Backup engine
- Rollback support
- Managed resources

### Phase 3

- Dependency validation
- Inventory system
- Advanced health checks

### Phase 4

- Web dashboard
- Multi-server support
- Cluster management
