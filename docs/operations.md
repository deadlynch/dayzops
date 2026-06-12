# Operations

## Daily Operations

### Server Status

```bash
dayzctl status
```

```bash
systemctl status dayz
```

---

## Server Control

### Start

```bash
dayzops start
```

### Stop

```bash
dayzops stop
```

### Restart

```bash
dayzops restart
```

---

## Mod Management

### Add Mod

```bash
dayzctl mod add <workshop-id>
```

Example:

```bash
dayzctl mod add 1559212036
```

### Remove Mod

```bash
dayzctl mod remove <workshop-id>
```

### List Mods

```bash
dayzctl mod list
```

### Synchronize Mods

```bash
dayzctl mod sync
```

This operation:

- Installs new mods
- Updates existing mods
- Removes deleted mods
- Rebuilds startup parameters
- Synchronizes keys

---

## Key Synchronization

```bash
dayzctl sync-keys
```

The operation:

1. Removes existing keys
2. Scans installed mods
3. Finds all .bikey files
4. Removes duplicates
5. Rebuilds keys directory

---

## Updates

```bash
dayzctl update
```

Workflow:

```text
backup
↓
stop
↓
update server
↓
update mods
↓
sync keys
↓
cleanup
↓
start
```

---

## Backups

Create backup:

```bash
dayzctl backup
```

List backups:

```bash
dayzctl backup list
```

Restore backup:

```bash
dayzctl rollback <backup-name>
```

---

## Validation

Validate configuration:

```bash
dayzctl validate-config
```

Validate installation:

```bash
dayzctl validate
```

---

## Health Checks

```bash
dayzctl healthcheck
```

Validation includes:

- Server process
- Required files
- Keys
- Mods
- Startup parameters
- Network ports

---

## Logs

Application logs:

```text
/srv/dayz/logs
```

System logs:

```bash
journalctl -u dayz
```

Follow logs:

```bash
journalctl -u dayz -f
```

---

## Troubleshooting

### Server Does Not Start

```bash
dayzctl validate
```

```bash
journalctl -u dayz -n 100
```

### Signature Errors

```bash
dayzctl sync-keys
```

### Mod Not Loading

```bash
dayzctl mod list
```

```bash
dayzctl mod sync
```

### Update Failure

```bash
journalctl -u dayz-update
```

```bash
dayzctl status
```
