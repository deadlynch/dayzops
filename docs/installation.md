# Installation

This is the detailed install reference. For a quick start, see the
[README](../README.md).

## Requirements

**Supported Linux:** Debian 12+, Ubuntu 24.04+, Rocky 9+, Arch / CachyOS.

**Dependencies** (the installer attempts to install these): `steamcmd`,
`bash`, `curl`, `tar`, `gzip`, `findutils`, `coreutils`, `rsync`, `systemd`.

**Steam account** owning DayZ — required for server installation and Workshop
mod downloads.

## Layout

Default installation root: `/srv/dayz`.

```text
/srv/dayz
├── backups/     # timestamped .tar.gz archives
├── config/      # server.yaml
├── server/      # DayZ dedicated server (+ @mod symlinks, keys/)
├── state/       # generated JSON state inventory
└── workshop/    # downloaded Workshop content
```

## Install

```bash
git clone https://github.com/deadlynch/dayzops.git
cd dayzops
sudo ./scripts/install.sh
```

The installer is idempotent and:

1. Creates the directory tree under `/srv/dayz`
2. Creates the `dayz` system user
3. Installs OS dependencies (best-effort; review SteamCMD on your distro)
4. Installs the `dayzops` package (the `dayzops` command lands on `PATH`)
5. Generates the systemd units (`dayz.service`, `dayz-update.{service,timer}`,
   `dayz-prune.{service,timer}`)
6. Writes a default `/srv/dayz/config/server.yaml`
7. Creates `/etc/dayzops.env` (protected, for the Steam password)
8. Enables the update and prune timers

Override defaults with environment variables:

```bash
sudo DAYZ_HOME=/opt/dayz DAYZ_USER=dayz SCHEDULE=05:00 ./scripts/install.sh
```

## Configure

Edit `/srv/dayz/config/server.yaml` (full example and field reference in the
[README](../README.md#configuration)). Then validate:

```bash
dayzops validate-config
```

### Steam password

The password is never stored in `server.yaml`. The installer creates
`/etc/dayzops.env` (mode 600, owned by `dayz`); add your password there:

```bash
sudoedit /etc/dayzops.env
# DAYZOPS_STEAM_PASSWORD=your_password
```

The `dayz-update.service` reads this file via `EnvironmentFile`. For manual
runs, export `DAYZOPS_STEAM_PASSWORD` in your shell. If the account uses Steam
Guard / 2FA, run one manual `dayzops update` first to authenticate
interactively and cache the credential.

## First startup

```bash
dayzops apply              # install server, sync mods + keys, write units
dayzops start              # or: sudo systemctl start dayz
dayzops status
```

## Verify

```bash
dayzops validate-config
systemctl status dayz
dayzops status
```
