# Operations

## Daily Operations

### Server Status

```bash
dayzops status
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
dayzops mod add <workshop-id>
```

Example:

```bash
dayzops mod add 1559212036
```

### Remove Mod

```bash
dayzops mod remove <workshop-id>
```

### List Mods

```bash
dayzops mod list
```

### Synchronize Mods

```bash
dayzops mod sync
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
dayzops sync-keys
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
dayzops update
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
dayzops backup
```

List backups:

```bash
dayzops backup list
```

Restore backup:

```bash
dayzops rollback <backup-name>
```

---

## Validation

Validate configuration:

```bash
dayzops validate-config
```

Validate installation:

```bash
dayzops validate
```

---

## Health Checks

```bash
dayzops healthcheck
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
dayzops validate
```

```bash
journalctl -u dayz -n 100
```

### Signature Errors

```bash
dayzops sync-keys
```

### Mod Not Loading

```bash
dayzops mod list
```

```bash
dayzops mod sync
```

### Update Failure

```bash
journalctl -u dayz-update
```

```bash
dayzops status
```
