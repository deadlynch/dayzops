# Installation

## Requirements

### Operating System

Supported Linux distributions:

- CachyOS
- Arch Linux
- Debian 12+
- Ubuntu 24.04+
- Rocky Linux 9+

### Dependencies

Required packages:

```bash
steamcmd
bash
curl
tar
gzip
findutils
coreutils
rsync
yq
systemd
```

### Steam Account

A Steam account owning DayZ is required for:

- DayZ Dedicated Server installation
- Workshop mod downloads
- Mod updates

---

## Installation Layout

Default installation path:

```text
/srv/dayz
```

Directory structure:

```text
/srv/dayz
├── backups/
├── bin/
├── config/
├── custom/
├── logs/
├── runtime/
├── server/
├── state/
└── workshop/
```

---

## Installation

Run:

```bash
sudo ./install.sh
```

The installer will:

1. Create required directories
2. Create dayz service user
3. Install SteamCMD dependencies
4. Install DayZ Dedicated Server
5. Generate systemd units
6. Create default configuration
7. Configure automatic updates

---

## Configuration

Main configuration file:

```text
/srv/dayz/config/server.yaml
```

Example:

```yaml
server:
  name: "Chernarus Vanilla++"

steam:
  username: "USERNAME"

mods: []

servermods: []

backup:
  retention_days: 14

logs:
  retention_days: 30
```

---

## Validate Installation

Verify configuration:

```bash
dayzops validate-config
```

Verify service:

```bash
systemctl status dayz
```

Verify server state:

```bash
dayzops status
```

---

## First Startup

Start server:

```bash
sudo systemctl start dayz
```

Or:

```bash
dayzops start
```

Verify logs:

```bash
journalctl -u dayz -f
```

---

## Automatic Updates

Enable update timer:

```bash
systemctl enable dayz-update.timer
systemctl start dayz-update.timer
```

Verify:

```bash
systemctl list-timers
```

The update workflow executes daily at 04:00 by default.
