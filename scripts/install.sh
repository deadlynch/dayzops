#!/usr/bin/env bash
#
# Instalador do dayzops. Idempotente: rodar de novo não duplica nada.
# Requer root (cria usuário de sistema, diretórios em /srv e units systemd).
#
# Variáveis sobrescrevíveis:
#   DAYZ_HOME  (default /srv/dayz)
#   DAYZ_USER  (default dayz)
#   SCHEDULE   (default 04:00 — horário do update automático)
#
set -euo pipefail

DAYZ_HOME="${DAYZ_HOME:-/srv/dayz}"
DAYZ_USER="${DAYZ_USER:-dayz}"
SCHEDULE="${SCHEDULE:-04:00}"
CONFIG="${DAYZ_HOME}/config/server.yaml"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '[install] %s\n' "$*"; }

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "Este instalador precisa de root. Rode: sudo ./scripts/install.sh" >&2
        exit 1
    fi
}

# 1) Diretórios
create_dirs() {
    log "criando estrutura em ${DAYZ_HOME}"
    local dirs=(backups bin config custom logs runtime server state workshop)
    for d in "${dirs[@]}"; do
        mkdir -p "${DAYZ_HOME}/${d}"
    done
    # subdir do server que o ExecStart referencia via -profiles=
    # (Bohemia: "Path to the folder containing server profile. By default,
    # server logs are written to the server profile's directory.")
    mkdir -p "${DAYZ_HOME}/server/profiles"
}

# 2) Usuário de serviço
create_user() {
    if id "${DAYZ_USER}" &>/dev/null; then
        log "usuário ${DAYZ_USER} já existe"
    else
        log "criando usuário de sistema ${DAYZ_USER}"
        useradd --system --home-dir "${DAYZ_HOME}" --shell /usr/sbin/nologin "${DAYZ_USER}"
    fi
    chown -R "${DAYZ_USER}:${DAYZ_USER}" "${DAYZ_HOME}"
}

# 3) Dependências de SO (best-effort, detecta apt/pacman)
install_deps() {
    local pkgs=(curl tar gzip rsync findutils coreutils)
    if command -v apt-get &>/dev/null; then
        log "instalando dependências via apt"
        apt-get update -qq && apt-get install -y "${pkgs[@]}" steamcmd || \
            log "AVISO: revise as dependências manualmente (steamcmd pode exigir repositório non-free)"
    elif command -v pacman &>/dev/null; then
        log "instalando dependências via pacman"
        pacman -Sy --noconfirm "${pkgs[@]}" || log "AVISO: instale steamcmd via AUR"
    else
        log "AVISO: gerenciador de pacotes não detectado; instale manualmente: ${pkgs[*]} steamcmd"
    fi
}

# 4) Pacote dayzops (instala o comando `dayzops` no PATH)
install_package() {
    log "instalando o pacote dayzops"
    pip install --break-system-packages "${REPO_ROOT}" || pip install "${REPO_ROOT}"
}

# 5) Units systemd (reaproveita o gerador do próprio dayzops)
generate_units() {
    log "gerando units systemd"
    python3 - "$DAYZ_HOME" "$SCHEDULE" <<'PY'
import sys
from dayzops.systemd import generate_units
home, schedule = sys.argv[1], sys.argv[2]
generate_units(
    "/etc/systemd/system",
    exec_start=f"{home}/server/DayZServer -config=serverDZ.cfg -port=2302",
    working_dir=f"{home}/server",
    schedule=schedule,
)
PY
    systemctl daemon-reload
}

# 6) Configuração default (não sobrescreve se já existir)
create_config() {
    if [[ -f "${CONFIG}" ]]; then
        log "config já existe em ${CONFIG} (mantido)"
        return
    fi
    log "criando config default em ${CONFIG}"
    cat > "${CONFIG}" <<YAML
server:
  name: "Chernarus Vanilla++"
  map: chernarus
  port: 2302

steam:
  username: "USERNAME"

paths:
  install_dir: ${DAYZ_HOME}/server
  workshop_dir: ${DAYZ_HOME}/workshop
  mods_dir: ${DAYZ_HOME}/server
  backups_dir: ${DAYZ_HOME}/backups
  state_dir: ${DAYZ_HOME}/state

mods: []
servermods: []

backup:
  retention_days: 14

updates:
  schedule: "${SCHEDULE}"
YAML
    chown "${DAYZ_USER}:${DAYZ_USER}" "${CONFIG}"
}

# 7) Arquivo de ambiente para a senha do Steam (referenciado pela unit de
#    update via EnvironmentFile). Criado vazio e protegido; o admin preenche.
create_env_file() {
    if [[ -f /etc/dayzops.env ]]; then
        log "/etc/dayzops.env já existe (mantido)"
        return
    fi
    log "criando /etc/dayzops.env (preencha com a senha do Steam)"
    install -m 600 -o "${DAYZ_USER}" -g "${DAYZ_USER}" /dev/null /etc/dayzops.env
    cat > /etc/dayzops.env <<'ENV'
# Senha do Steam usada pelo SteamCMD (lida pelo dayz-update.service).
# NÃO versione este arquivo. Preencha a linha abaixo:
# DAYZOPS_STEAM_PASSWORD=suasenha
ENV
    chmod 600 /etc/dayzops.env
    chown "${DAYZ_USER}:${DAYZ_USER}" /etc/dayzops.env
}

# 8) Agendamentos automáticos (habilita os timers)
enable_updates() {
    log "habilitando os timers de update e prune"
    systemctl enable --now dayz-update.timer dayz-prune.timer || \
        log "AVISO: não foi possível habilitar os timers (systemd indisponível?)"
}

# Reafirma o dono de toda a árvore como o usuário de serviço. Passos anteriores
# (pip, geração de units, cópia de config) rodam como root e podem deixar
# arquivos com dono root dentro de ${DAYZ_HOME}; o servidor roda como
# ${DAYZ_USER} e precisa ler/gravar tudo ali. Idempotente.
fix_ownership() {
    log "ajustando dono de ${DAYZ_HOME} para ${DAYZ_USER}:${DAYZ_USER}"
    chown -R "${DAYZ_USER}:${DAYZ_USER}" "${DAYZ_HOME}"
}

main() {
    require_root
    create_dirs
    create_user
    install_deps
    install_package
    generate_units
    create_config
    create_env_file
    enable_updates
    fix_ownership
    log "concluído. Edite ${CONFIG} (usuário Steam e mods) e /etc/dayzops.env (senha), depois rode: dayzops validate-config"
}

main "$@"
