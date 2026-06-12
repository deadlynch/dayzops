# Operations

Day-to-day runbook. For installation and configuration, see the
[README](../README.md).

## Status

```bash
dayzops status            # service state, mod count, last update/backup
systemctl status dayz     # systemd view of the server unit
```

## Server control

```bash
dayzops start
dayzops stop
dayzops restart
```

These wrap `systemctl {start,stop,restart} dayz`.

## Reconcile (declarative)

```bash
dayzops apply --dry-run   # show what would change
dayzops apply             # converge the system to server.yaml
```

`apply` installs the server if missing, syncs mod symlinks, rebuilds keys and
writes the systemd units — only for what diverged. It is idempotent.

## Updates

```bash
dayzops update            # runs nightly via dayz-update.timer
```

Atomic workflow, under a global lock, with automatic rollback:

```text
lock → backup → stop → update server → update mods → validate
     → rebuild keys → start → health check
```

If validation fails, the backup is restored and the previous version is
brought back up.

## Mods

```bash
dayzops mod list
dayzops mod add 1559212036 --name CF     # client mod (--server for servermods)
dayzops mod remove 1559212036
```

After changing the mod list, run `dayzops apply` to converge symlinks and keys.
Keys are rebuilt automatically during `apply` and `update` — there is no
separate key command (full rebuild, per ADR-0004).

## Backups

```bash
dayzops backup            # create a backup now
dayzops rollback          # restore the most recent backup and start the server
dayzops prune             # delete backups older than backup.retention_days
```

Backups are timestamped `.tar.gz` archives under `backups_dir`. Pruning also
runs nightly via `dayz-prune.timer`.

## Validation

```bash
dayzops validate-config   # check server.yaml (required fields, types)
```

Installation readiness (binary, config, mod content present) is validated
automatically as a step inside `update`; it is not a separate command.

## Logs

```bash
journalctl -u dayz -f          # server logs (live)
journalctl -u dayz-update      # scheduled update logs
journalctl -u dayz-prune       # scheduled prune logs
```

dayzops writes its own operational logs to stderr, captured by journald.

## Troubleshooting

**Server does not start** — check readiness and logs:

```bash
dayzops status
journalctl -u dayz -n 100
```

**Signature / key errors** — rebuild keys by reconciling:

```bash
dayzops apply
```

**Mod not loading** — confirm it is declared and converged:

```bash
dayzops mod list
dayzops apply --dry-run
```

**Update failed** — the rollback is automatic; inspect why:

```bash
journalctl -u dayz-update -n 100
dayzops status
```
