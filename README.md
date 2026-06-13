# DayZops

**Declarative DayZ server management for Linux.**

DayZops manages the full lifecycle of a DayZ dedicated server — install,
updates, mods, keys, backups and the systemd service — from a single
declarative configuration file. Instead of juggling disconnected shell
scripts, you describe the desired state in `server.yaml` and let DayZops
converge the system to match it.

## Core principles

- **Single source of truth.** Everything is defined in one file:
  `/srv/dayz/config/server.yaml`. Startup parameters, mod symlinks, key
  directory and systemd units are generated from it.
- **Declarative & idempotent.** `dayzops apply` reads the config, compares it
  to the current state and changes only what diverged. Running it twice does
  nothing the second time.
- **Atomic updates.** Updates run under a global lock with an automatic
  rollback: if validation fails, the previous version is restored.

## Requirements

- A supported Linux distribution: Debian 12+, Ubuntu 24.04+, Rocky 9+, Arch /
  CachyOS.
- Root access (the installer creates a system user, directories under `/srv`
  and systemd units).
- A **Steam account that owns DayZ** (required to download the dedicated
  server and Workshop mods).

## Installation

```bash
git clone https://github.com/deadlynch/dayzops.git
cd dayzops
sudo ./scripts/install.sh
```

The installer is idempotent and performs seven steps: creates the directory
tree under `/srv/dayz`, the `dayz` system user, installs OS dependencies
(`steamcmd`, `rsync`, …), installs the `dayzops` package, generates the
systemd units, writes a default `server.yaml`, and enables the update and
prune timers.

Override defaults with environment variables:

```bash
sudo DAYZ_HOME=/opt/dayz SCHEDULE=05:00 ./scripts/install.sh
```

For development you can run from the repository without installing, using the
shim:

```bash
./bin/dayzops version
```

## Configuration

The configuration file lives at `/srv/dayz/config/server.yaml`.

```yaml
server:
  name: "My Chernarus Server"
  map: chernarus
  port: 2302

steam:
  username: "your_steam_username"   # password is NOT stored here (see below)

instance:
  config: serverDZ.cfg

paths:
  install_dir: /srv/dayz/server
  workshop_dir: /srv/dayz/workshop
  mods_dir: /srv/dayz/server
  backups_dir: /srv/dayz/backups
  state_dir: /srv/dayz/state

mods:                               # order = load order
  - id: 1559212036
    name: "@CF"
servermods: []

backup:
  retention_days: 14

updates:
  schedule: "04:00"
  prune_schedule: "05:00"
```

**Required fields:** `server.name`, `server.map`, `server.port`,
`steam.username`, and all of `paths.*`. Validate after editing:

```bash
dayzops validate-config
```

### Steam password

By design the Steam password is **never** stored in `server.yaml`. It is read
from the `DAYZOPS_STEAM_PASSWORD` environment variable and is redacted from
logs.

For manual runs:

```bash
export DAYZOPS_STEAM_PASSWORD='your_password'
```

For the scheduled update timer, put the password in `/etc/dayzops.env`
(created by the installer, mode 600, owned by `dayz`). The
`dayz-update.service` reads it automatically via `EnvironmentFile`:

```bash
sudoedit /etc/dayzops.env
# DAYZOPS_STEAM_PASSWORD=your_password
```

If the account uses Steam Guard / 2FA, the first SteamCMD login is
interactive — run a manual `dayzops update` once to authenticate and cache the
credential.

## Usage

### First launch

```bash
dayzops apply --dry-run    # show what would change, without touching anything
dayzops apply              # install server, sync mods + keys, write units
dayzops start              # or: sudo systemctl start dayz
dayzops status
```

`apply` is the declarative path: it reconciles the running system with
`server.yaml`. It is safe to run repeatedly.

### Day to day

```bash
dayzops update             # atomic update (see below), runs nightly via timer
dayzops backup             # create a backup now
dayzops rollback           # restore the latest backup and bring the server up
dayzops prune              # delete backups older than backup.retention_days
journalctl -u dayz -f      # follow server logs
```

### Managing mods

```bash
dayzops mod list
dayzops mod add 1559212036 --name CF      # add a client mod
dayzops mod add 9999999999 --server       # add a server mod
dayzops mod remove 1559212036
```

Mods are added to `server.yaml` in declaration order, which is the load order.
Run `dayzops apply` afterwards to converge the symlinks and keys.

### The atomic update workflow

`dayzops update` runs the full sequence under a global lock, with automatic
rollback on failure:

```text
lock → backup → stop → update server → update mods → validate
     → rebuild keys → start → health check
```

If validation fails, the backup is restored and the previous version is
brought back up — the server is never left in an unusable state.

## Command reference

| Command | Description |
|---|---|
| `dayzops version` | Print version |
| `dayzops validate-config` | Validate `server.yaml` |
| `dayzops status` | Show service, mod count, last update/backup |
| `dayzops apply [--dry-run]` | Reconcile the system with the config |
| `dayzops update` | Atomic update with rollback |
| `dayzops backup` | Create a backup |
| `dayzops rollback` | Restore the latest backup |
| `dayzops prune` | Remove backups past retention |
| `dayzops start` / `stop` / `restart` | Control the service |
| `dayzops mod list` / `add` / `remove` | Manage the mod list |

Use `-c PATH` (before the command) to point at a config other than the
default, e.g. `dayzops -c ./server.yaml validate-config`.

## Architecture

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

## Directory structure

```text
/srv/dayz
├── backups/     # timestamped .tar.gz backups
├── config/      # server.yaml
├── server/      # DayZ dedicated server install (+ @mod symlinks, keys/)
├── state/       # generated state inventory (JSON)
└── workshop/    # downloaded Workshop content
```

## License

MIT
