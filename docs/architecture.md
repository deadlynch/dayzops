# Architecture

## Overview

DayZops is a declarative management platform for Linux-hosted DayZ dedicated
servers. It centralizes the server lifecycle into a single control plane:
installation, mod and key synchronization, updates, backups, rollback,
service control and state tracking — all driven from one configuration file.

## Design principles

- **Single source of truth.** All desired state lives in
  `/srv/dayz/config/server.yaml`. Startup parameters, mod symlinks, the key
  directory and the systemd units are generated from it.
- **Declarative & idempotent.** Administrators declare the desired state;
  `dayzops apply` reconciles the actual state, changing only what diverged.
- **Atomic updates.** Updates run under a global lock with automatic rollback.
- **Linux native.** Built around systemd, SteamCMD, symlinks and journald.

## Module map

| Module | Responsibility |
|---|---|
| `config` | Load and validate `server.yaml` |
| `steamcmd` | Install/update server and download mods |
| `mods` | Symlink-based mod management + startup params |
| `keys` | Full `.bikey` directory rebuild |
| `backup` | Create/restore/prune backups |
| `systemd` | Generate units, control the service |
| `state` | Persisted state inventory (JSON) |
| `lock` | Global `flock`-based mutual exclusion |
| `logger` | Structured logging to stderr/journald |
| `verify` / `health` | Pre-start validation and readiness check |
| `ops` | Atomic update workflow with rollback |
| `apply` | Declarative reconciliation |
| `app` / `cli` | Composition root and command-line interface |

## High-level flow

```text
server.yaml
      │
      ▼
   dayzops
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

## Configuration model

```yaml
server:
  name: "My DayZ Server"
  map: chernarus
  port: 2302

steam:
  username: "steamuser"      # password via DAYZOPS_STEAM_PASSWORD, never here

paths:
  install_dir: /srv/dayz/server
  workshop_dir: /srv/dayz/workshop
  mods_dir: /srv/dayz/server
  backups_dir: /srv/dayz/backups
  state_dir: /srv/dayz/state

mods: []
servermods: []

backup:
  retention_days: 14

updates:
  schedule: "04:00"
  prune_schedule: "05:00"
```

Required keys: `server.name/map/port`, `steam.username`, all `paths.*`.

## Update workflow (ADR-0006)

```text
acquire lock → create backup → stop server → update server → update mods
→ validate → rebuild keys → start server → health check → release lock
```

On validation failure: restore backup → start previous version.

## Mod management (ADR-0003/0007/0008)

Workshop content lives in `workshop/<id>`; the server gets symlinks
`@Name -> workshop/<id>`. Load order equals declaration order in
`server.yaml`. Client (`-mod=`) and server (`-serverMod=`) lists are
generated independently.

## Key management (ADR-0004)

Mods place `.bikey` files in inconsistent locations. DayZops performs a full
rebuild: clear the key directory, discover all `*.bikey` recursively
(case-insensitive), de-duplicate, and rebuild. This avoids orphaned/stale keys.

## Backup strategy (ADR-0005)

Backed-up scope (relative to the server install): `profiles/`, `mpmissions/`
(including world persistence under `storage_*`), `battleye/`, `config/`,
`custom/`, `serverDZ.cfg`. Archives are written atomically and restored with
path-traversal protection.

## State management (ADR-0010)

Generated inventories under `/srv/dayz/state`, written atomically and never
edited by hand:

```text
installed-mods.json
installed-keys.json
last-backup.json
last-update.json
inventory.json
```

## Locking (ADR-0009)

A global `fcntl.flock` on `/run/dayzops.lock` serializes critical operations
(update, backup, rollback, apply). The lock is held via the file descriptor,
so it is released by the kernel if the process dies — no stale locks.

## Logging

Structured logs go to stderr and are captured by journald
(`journalctl -u dayz`). Level is controlled by `DAYZOPS_LOG_LEVEL`.

## Not yet implemented

Declarative file deployment (`managed_files` / `managed_dirs`) appears in some
early examples but is **not implemented** yet. Possible future work: a Source
(A2S) query in the health check, multi-server fleet management, and a build /
publish pipeline on release tags.

See [implementation-notes.md](implementation-notes.md) for where the code
refined the original ADRs.
