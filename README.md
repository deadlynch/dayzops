# DayZops

**Declarative DayZ server management for Linux.**

DayZops manages the full lifecycle of a DayZ dedicated server — install,
updates, mods, keys, backups and the systemd service — from a single
declarative configuration file. Instead of juggling disconnected shell scripts,
you describe the desired state in `server.yaml` and let DayZops converge the
system to match it.

## Core principles

- **Single source of truth.** Everything is defined in one file:
  `/srv/dayz/config/server.yaml`. Startup parameters, mod symlinks, key
  directory and systemd units are generated from it.
- **Declarative & idempotent.** `dayzops apply` reads the config, compares it to
  the current state and changes only what diverged. Running it twice does
  nothing the second time.
- **Atomic updates.** Updates run under a global lock with an automatic
  rollback: if validation fails, the previous version is restored.

## Requirements

- A supported Linux distribution: **Debian 12+**, **Ubuntu 24.04 / 26.04**, or
  **Arch / CachyOS**.
- A 64-bit host with **i386 multiarch** available (SteamCMD ships as a 32-bit
  binary). The installer enables this for you.
- Root access — the installer creates a system user, directories under `/srv`,
  and systemd units.
- **A Steam account that owns DayZ.** Unlike most dedicated servers, the DayZ
  server build (app `223350`) is **not** available via anonymous login; you
  must authenticate with an account that owns the game. Workshop mods are pulled
  via the client app `221100`.

## Installation

```
git clone https://github.com/deadlynch/dayzops.git
cd dayzops
sudo ./scripts/install.sh
```

The installer is idempotent (safe to re-run) and, in order:

1. Detects the distribution (apt- or pacman-based).
2. Creates the directory tree under `/srv/dayz` and the `dayz` system user.
3. Installs OS dependencies. On Debian/Ubuntu it enables the `i386` architecture
   and installs `rsync`, `python3-venv`, `python3-pip`, `lib32gcc-s1`, …; on Arch
   it enables the `multilib` repo and installs the equivalents.
4. Installs **SteamCMD** from Valve's official tarball into
   `/srv/dayz/steamcmd`. SteamCMD is deliberately **not** installed from distro
   packages — it is absent from the default repositories on every supported
   distro (Debian `non-free`, Ubuntu `multiverse`, Arch AUR), so the tarball is
   the portable, identical-everywhere path.
5. Installs the `dayzops` package into a dedicated virtualenv at
   `/srv/dayz/.venv` and exposes the `dayzops` command via a symlink in
   `/usr/local/bin`. The virtualenv avoids the `externally-managed-environment`
   (PEP 668) restriction on modern distros and keeps the system Python clean.
6. Generates the systemd units, writes a default `server.yaml`, creates
   `/etc/dayzops.env` (mode 600) for the Steam password, and enables the update
   and prune timers.

Override defaults with environment variables:

```
sudo DAYZ_HOME=/opt/dayz SCHEDULE=05:00 ./scripts/install.sh
```

For development you can run from the repository without installing, using the
shim:

```
./bin/dayzops version
```

> **SteamCMD path.** DayZops locates the SteamCMD binary automatically
> (`/srv/dayz/steamcmd/steamcmd.sh` first, then the system PATH). It always runs
> SteamCMD as the `dayz` user via `sudo -H -u dayz`, never as root — this keeps
> the Steam cache under the service user's home and avoids root-owned
> `~/.steam` directories that would break later updates.

## Steam authentication & Steam Guard

The password is read from the `DAYZOPS_STEAM_PASSWORD` environment variable (or
`/etc/dayzops.env`) and is **never** stored in `server.yaml`. It is redacted
from logs, along with the account name. How the first login behaves depends on
whether the account uses Steam Guard.

### Account without Steam Guard

Nothing interactive is required:

```
sudoedit /etc/dayzops.env        # uncomment: DAYZOPS_STEAM_PASSWORD=yourpassword
sudo dayzops apply
```

DayZops logs in non-interactively and downloads the server. If the password is
missing or wrong, `apply` fails immediately with an actionable message — it does
not hang on a prompt.

### Account with Steam Guard (email code or authenticator / TOTP)

The Guard code rotates, so it cannot be fully automated reliably. You
authenticate **once per machine/account**; SteamCMD then caches a session token
(`ssfn*` + `config.vdf`) under the service user's home (`/srv/dayz/.steam`), and
every later `apply` / `update` / timer run reuses it without asking again:

```
sudoedit /etc/dayzops.env        # set DAYZOPS_STEAM_PASSWORD first
sudo dayzops steam-login         # interactive: type the Guard code once
sudo dayzops apply               # finds the cached token, no prompt
```

`steam-login` inherits the terminal so the Guard prompt shows correctly, and
runs SteamCMD as the `dayz` user with the right `HOME`, so the cached token
lands exactly where the automated runs look for it.

### Under the automated timer

`dayz-update.timer` runs with no TTY. With a valid cached token the update runs
unattended. If the account requires Guard and no token is cached yet, the run
fails fast and tells you to run `sudo dayzops steam-login` once. The same
applies if the token later expires or Steam invalidates the session (e.g. after
a password change) — re-running `steam-login` refreshes the cache. Treat this as
occasional maintenance, not a tool failure.

## Configuration

The configuration file lives at `/srv/dayz/config/server.yaml`.

```yaml
server:
  name: "My Chernarus Server"
  map: chernarus
  port: 2302

steam:
  username: "your_steam_username"   # password is NOT stored here (see above)

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

```
dayzops validate-config
```

## Usage

### First launch

```
dayzops apply --dry-run    # show what would change, without touching anything
dayzops apply              # install server, sync mods + keys, write units
dayzops start              # or: sudo systemctl start dayz
dayzops status
```

`apply` is the declarative path: it reconciles the running system with
`server.yaml`. It is safe to run repeatedly.

### Day to day

```
dayzops update             # atomic update (see below), runs nightly via timer
dayzops backup             # create a backup now
dayzops rollback           # restore the latest backup and bring the server up
dayzops prune              # delete backups older than backup.retention_days
journalctl -u dayz -f      # follow server logs
```

### Managing mods

```
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

```
lock → backup → stop → update server → update mods → validate
     → rebuild keys → start → health check
```

If validation fails, the backup is restored and the previous version is brought
back up — the server is never left in an unusable state.

## Command reference

| Command                               | Description                                 |
| ------------------------------------- | ------------------------------------------- |
| `dayzops version`                     | Print version                               |
| `dayzops validate-config`             | Validate `server.yaml`                      |
| `dayzops status`                      | Show service, mod count, last update/backup |
| `dayzops apply [--dry-run]`           | Reconcile the system with the config        |
| `dayzops update`                      | Atomic update with rollback                 |
| `dayzops steam-login`                 | One-time interactive Steam login (caches Guard) |
| `dayzops backup`                      | Create a backup                             |
| `dayzops rollback`                    | Restore the latest backup                   |
| `dayzops prune`                       | Remove backups past retention               |
| `dayzops start` / `stop` / `restart`  | Control the service                         |
| `dayzops mod list` / `add` / `remove` | Manage the mod list                         |
| `dayzops render-config`               | Render a default `server.yaml`              |

Use `-c PATH` (before the command) to point at a config other than the default,
e.g. `dayzops -c ./server.yaml validate-config`.

## Troubleshooting

### `Package 'steamcmd' has no installation candidate`

You are installing SteamCMD from distro packages, which DayZops avoids on
purpose — it is not in the default repository on any supported distro. Let the
installer fetch the official tarball (`sudo ./scripts/install.sh`), or install
it manually into `/srv/dayz/steamcmd`.

### `pip: command not found` / `externally-managed-environment`

`pip` is not installed or the system Python is PEP 668 "externally managed"
(default on Debian 12+ / Ubuntu 24.04+). The installer sidesteps both by using a
virtualenv at `/srv/dayz/.venv`; if you run something by hand, call the venv's
interpreter (`/srv/dayz/.venv/bin/dayzops`).

### `sudo: 'steamcmd': command not found`

An older build invoked SteamCMD by bare name, which `sudo`'s restricted
`secure_path` cannot resolve. Current DayZops uses the absolute path it
auto-detects (`/srv/dayz/steamcmd/steamcmd.sh`). Re-install
(`sudo ./scripts/install.sh`) so the binary exists at that path.

### Login problems

- **`Invalid Password` / credential refused** — the password in
  `/etc/dayzops.env` is wrong or still commented out (the line must not start
  with `#`).
- **`Rate Limit Exceeded`** — too many failed attempts; Steam temporarily blocks
  the IP. Wait ~30 minutes, fix the password, then retry.
- **`No subscription`** — the account does not own DayZ; the server build is only
  available to accounts that own the game.
- **The account requires Steam Guard** — run `sudo dayzops steam-login` once to
  cache the token (see *Steam authentication* above).
- **Login fails with the password correct** — check the system clock; an
  out-of-sync clock breaks the Steam handshake. Run
  `sudo timedatectl set-ntp true` and confirm `System clock synchronized: yes`.

### `Pending kernel upgrade`

Cosmetic for DayZops, but reboot before first launch so the server starts on the
current kernel: `sudo reboot`.

## Architecture

```
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

```
/srv/dayz
├── .venv/       # virtualenv com o pacote dayzops
├── backups/     # timestamped .tar.gz backups
├── config/      # server.yaml
├── logs/        # logs do dayzops
├── server/      # DayZ dedicated server install (+ @mod symlinks, keys/)
├── state/       # generated state inventory (JSON)
├── steamcmd/    # SteamCMD (tarball oficial da Valve)
└── workshop/    # downloaded Workshop content
```

## License

MIT
