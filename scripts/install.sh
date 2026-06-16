#!/usr/bin/env bash
#
# Instalador do dayzops. Idempotente: rodar de novo não duplica nada.
# Requer root (cria usuário de sistema, diretórios em /srv e units systemd).
#
# Distros suportadas: Debian 12+, Ubuntu 24.04/26.04, Arch / CachyOS.
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
VENV="${DAYZ_HOME}/.venv"
STEAMCMD_DIR="${DAYZ_HOME}/steamcmd"
STEAMCMD_URL="https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PKG_FAMILY=""   # preenchido por detect_distro: "apt" | "pacman"

log() { printf '[install] %s\n' "$*"; }
die() { printf '[install] ERRO: %s\n' "$*" >&2; exit 1; }

# Executa um comando como o usuário de serviço (sem shell de login; funciona
# mesmo com shell nologin). runuser faz parte do util-linux — presente em
# qualquer distro, e não depende do sudo estar instalado.
as_dayz() { runuser -u "${DAYZ_USER}" -- "$@"; }

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        die "este instalador precisa de root. Rode: sudo ./scripts/install.sh"
    fi
}

# 0) Detecta a família de gerenciador de pacotes.
detect_distro() {
    if command -v apt-get &>/dev/null; then
        PKG_FAMILY="apt"
    elif command -v pacman &>/dev/null; then
        PKG_FAMILY="pacman"
    else
        die "gerenciador de pacotes não suportado (esperado apt ou pacman)."
    fi
    local name="desconhecida"
    [[ -r /etc/os-release ]] && name="$(. /etc/os-release; echo "${PRETTY_NAME:-$ID}")"
    log "distro detectada: ${name} (família ${PKG_FAMILY})"
}

# 1) Diretórios
create_dirs() {
    log "criando estrutura em ${DAYZ_HOME}"
    local dirs=(backups bin config custom logs runtime server state workshop)
    for d in "${dirs[@]}"; do
        mkdir -p "${DAYZ_HOME}/${d}"
    done
    # subdir do server que o ExecStart referencia via -profiles=
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

# 3) Dependências de SO.
#    SteamCMD é 32-bit, então habilitamos multiarch i386 / multilib e o
#    lib32gcc. NÃO instalamos steamcmd pelo gerenciador de pacotes: ele não
#    está no repositório padrão de nenhuma das distros suportadas (Debian:
#    non-free; Ubuntu: multiverse; Arch: AUR). Em vez disso usamos o tarball
#    oficial (ver install_steamcmd), que é idêntico nas três.
install_deps() {
    case "${PKG_FAMILY}" in
    apt)
        log "habilitando arquitetura i386 e instalando dependências (apt)"
        dpkg --add-architecture i386
        apt-get update -qq
        apt-get install -y \
            curl tar gzip rsync ca-certificates \
            python3 python3-venv python3-pip \
            lib32gcc-s1
        ;;
    pacman)
        log "habilitando repositório multilib e instalando dependências (pacman)"
        # multilib é necessário para lib32-gcc-libs. Descomenta o bloco
        # [multilib] em /etc/pacman.conf de forma idempotente.
        if ! grep -q '^\[multilib\]' /etc/pacman.conf; then
            log "ativando [multilib] em /etc/pacman.conf"
            sed -i '/^#\[multilib\]/,/^#Include/ s/^#//' /etc/pacman.conf
        fi
        pacman -Sy --noconfirm --needed \
            curl tar gzip rsync ca-certificates \
            python python-pip \
            lib32-gcc-libs
        ;;
    esac
}

# 4) SteamCMD via tarball oficial (portável entre distros).
#    Instalado em ${STEAMCMD_DIR}, de posse do usuário de serviço. Um wrapper
#    em /usr/local/bin/steamcmd garante que o binário resolva mesmo sob o
#    secure_path restrito do sudo, e força a execução como ${DAYZ_USER} (nunca
#    root — evita ~/.steam de dono root, que quebra updates futuros).
install_steamcmd() {
    log "instalando SteamCMD em ${STEAMCMD_DIR}"
    as_dayz mkdir -p "${STEAMCMD_DIR}"
    if [[ ! -x "${STEAMCMD_DIR}/steamcmd.sh" ]]; then
        as_dayz bash -c "curl -sqL '${STEAMCMD_URL}' | tar -xz -C '${STEAMCMD_DIR}'" \
            || die "falha ao baixar/extrair o SteamCMD de ${STEAMCMD_URL}"
    fi
    # Primeira execução: o SteamCMD se auto-atualiza. Pode retornar código !=0
    # de forma benigna nesse primeiro update, então não abortamos por isso.
    as_dayz "${STEAMCMD_DIR}/steamcmd.sh" +quit \
        || log "AVISO: primeira execução do SteamCMD retornou erro (normal no self-update inicial)"

    log "criando wrapper /usr/local/bin/steamcmd"
    cat > /usr/local/bin/steamcmd <<EOF
#!/usr/bin/env bash
# Gerado pelo instalador do dayzops. Resolve o SteamCMD e o roda como
# ${DAYZ_USER}. Se invocado como root (ex.: via sudo), dropa privilégio.
set -euo pipefail
TARGET="${STEAMCMD_DIR}/steamcmd.sh"
if [[ "\${EUID}" -eq 0 ]]; then
    exec runuser -u "${DAYZ_USER}" -- "\${TARGET}" "\$@"
fi
exec "\${TARGET}" "\$@"
EOF
    chmod 755 /usr/local/bin/steamcmd
}

# 5) Pacote dayzops em uma virtualenv dedicada.
#    Evita o erro "externally-managed-environment" (PEP 668) e não depende de
#    um comando `pip` global. O comando `dayzops` é exposto no PATH via symlink
#    em /usr/local/bin (que está no secure_path do sudo).
install_package() {
    log "criando virtualenv em ${VENV} e instalando o pacote dayzops"
    python3 -m venv "${VENV}"
    "${VENV}/bin/pip" install --upgrade pip >/dev/null
    "${VENV}/bin/pip" install "${REPO_ROOT}"
    ln -sf "${VENV}/bin/dayzops" /usr/local/bin/dayzops
    command -v dayzops >/dev/null || die "dayzops não ficou disponível no PATH após a instalação"
}

# 6) Units systemd (reaproveita o gerador do próprio dayzops, via venv)
generate_units() {
    log "gerando units systemd"
    "${VENV}/bin/python" - "$DAYZ_HOME" "$SCHEDULE" <<'PY'
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

# 7) Configuração default (não sobrescreve se já existir).
create_config() {
    if [[ -f "${CONFIG}" ]]; then
        log "config já existe em ${CONFIG} (mantido)"
        return
    fi
    log "renderizando config default em ${CONFIG}"
    mkdir -p "$(dirname "${CONFIG}")"
    if ! dayzops render-config \
        --output "${CONFIG}" \
        --dayz-home "${DAYZ_HOME}" \
        --schedule "${SCHEDULE}" > /dev/null; then
        die "dayzops render-config falhou; verifique a instalação do pacote"
    fi
    chown "${DAYZ_USER}:${DAYZ_USER}" "${CONFIG}"
}

# 8) Arquivo de ambiente para a senha do Steam (lido pela unit de update).
create_env_file() {
    if [[ -f /etc/dayzops.env ]]; then
        log "/etc/dayzops.env já existe (mantido)"
        return
    fi
    log "criando /etc/dayzops.env (preencha com a senha do Steam)"
    install -m 600 -o "${DAYZ_USER}" -g "${DAYZ_USER}" /dev/null /etc/dayzops.env
    cat > /etc/dayzops.env <<'ENV'
# Senha do Steam usada pelo SteamCMD (lida pelo dayz-update.service).
# Lembrete: o servidor DayZ (app 223350) NÃO aceita login anônimo — use uma
# conta Steam que possua o jogo. NÃO versione este arquivo.
# DAYZOPS_STEAM_PASSWORD=suasenha
ENV
    chmod 600 /etc/dayzops.env
    chown "${DAYZ_USER}:${DAYZ_USER}" /etc/dayzops.env
}

# 9) Agendamentos automáticos (habilita os timers)
enable_updates() {
    log "habilitando os timers de update e prune"
    systemctl enable --now dayz-update.timer dayz-prune.timer || \
        log "AVISO: não foi possível habilitar os timers (systemd indisponível?)"
}

# Reafirma o dono de toda a árvore como o usuário de serviço. Passos anteriores
# (venv, geração de units, render de config) rodam como root e podem deixar
# arquivos de dono root dentro de ${DAYZ_HOME}. Idempotente.
fix_ownership() {
    log "ajustando dono de ${DAYZ_HOME} para ${DAYZ_USER}:${DAYZ_USER}"
    chown -R "${DAYZ_USER}:${DAYZ_USER}" "${DAYZ_HOME}"
}

main() {
    require_root
    detect_distro
    create_dirs
    create_user
    install_deps
    install_steamcmd
    install_package
    generate_units
    create_config
    create_env_file
    enable_updates
    fix_ownership
    log "concluído. Edite ${CONFIG} (usuário Steam e mods) e /etc/dayzops.env (senha), depois rode: dayzops validate-config"
}

main "$@"
