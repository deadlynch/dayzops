# DayZops

Declarative DayZ Server Management for Linux

DayZops is a Linux-native management platform for DayZ dedicated servers focused on reliability, reproducibility and operational simplicity.

Instead of maintaining multiple disconnected scripts for startup, updates, backups, mod management and key synchronization, DayZops provides a single control plane that manages the entire server lifecycle from a declarative configuration file.

## Core Principles

### Single Source of Truth

All server state is defined in a single configuration file:

```yaml
/srv/dayz/config/server.yaml
```

Startup, updates, backups, mod synchronization and runtime configuration are generated from this file.

## Features

### Server Management

- Install DayZ Dedicated Server
- Start server
- Stop server
- Restart server
- Health checks
- Status reporting

### Workshop Management

- Install mods
- Remove mods
- Update mods
- Validate mods
- Automatic startup parameter generation

## Architecture

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

## Configuration Example

```yaml
server:
  name: "Chernarus Vanilla++"

steam:
  username: "USERNAME"

mods:
  - id: 1559212036

servermods: []

backup:
  retention_days: 14

logs:
  retention_days: 30

managed_files: []

managed_dirs: []
```

## Commands

```bash
dayzctl start
dayzctl stop
dayzctl restart
dayzctl update
dayzctl backup
dayzctl rollback
dayzctl validate
dayzctl status
```

### Mod Management

```bash
dayzctl mod add <workshop-id>
dayzctl mod remove <workshop-id>
dayzctl mod list
dayzctl mod sync
```

## License

MIT
