from pathlib import Path

APP_NAME = "dayzops"

# Caminho padrão de produção (ver README.md e docs/installation.md).
# Antes apontava para "server.yaml" (relativo ao cwd), o que divergia da doc.
# Agora alinhado à doc; pode ser sobrescrito na CLI com -c/--config.
DEFAULT_CONFIG = Path("/srv/dayz/config/server.yaml")

STATE_DIR = Path("/srv/dayz/state")

LOCK_FILE = Path("/run/dayzops.lock")
