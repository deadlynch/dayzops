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
#    Instalado em ${STEAMCMD_DIR}, de posse do usuário de serviço. O dayzops
#    descobre esse caminho sozinho (steamcmd._default_steamcmd_path procura
#    ${STEAMCMD_DIR}/steamcmd.sh primeiro) ou via paths.steamcmd_bin no
#    server.yaml — então NÃO precisa de wrapper em /usr/local/bin nem depender
#    do PATH do sudo. O steamcmd é sempre executado como ${DAYZ_USER} pelo
#    próprio dayzops (sudo -H -u ${DAYZ_USER}), evitando ~/.steam de dono root.
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
    mkdir -p /usr/local/bin
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

# --- Provisionamento interativo (credenciais, apply e serverDZ.cfg) ----------
# Roda só com terminal (TTY) e quando não está em modo não-interativo. Em
# automação/CI (DAYZOPS_NONINTERACTIVE=1 ou sem TTY) imprime os passos manuais
# e não bloqueia. Tudo idempotente.

# Lê o valor atual de uma chave simples do server.yaml (1ª ocorrência).
_yaml_value() {
    local key="$1"
    grep -oP "^\s*${key}:\s*\"?\K[^\"]*" "${CONFIG}" 2>/dev/null | head -1
}

set_username() {
    local current new
    current="$(_yaml_value username)"
    if [[ -n "${current}" && "${current}" != "USERNAME" ]]; then
        read -r -p "Usuário Steam atual é '${current}'. Trocar? (deixe vazio p/ manter): " new || new=""
    else
        read -r -p "Usuário Steam (conta que POSSUI o DayZ): " new || new=""
    fi
    [[ -z "${new}" ]] && { log "usuário Steam mantido: '${current:-<vazio>}'"; return; }
    # Substitui o valor da chave username (sob steam:). Usernames do Steam são
    # alfanuméricos, então sem necessidade de escaping pesado.
    sed -i -E "s|^([[:space:]]*username:[[:space:]]*).*|\1\"${new}\"|" "${CONFIG}"
    chown "${DAYZ_USER}:${DAYZ_USER}" "${CONFIG}"
    log "usuário Steam definido: '${new}'"
}

set_password() {
    local has_pw pw pw2
    has_pw="$(grep -E '^[[:space:]]*DAYZOPS_STEAM_PASSWORD=.+' /etc/dayzops.env 2>/dev/null || true)"
    if [[ -n "${has_pw}" ]]; then
        local ans
        read -r -p "Senha do Steam já configurada. Trocar? (s/N): " ans || ans=""
        [[ "${ans}" != "s" && "${ans}" != "S" ]] && { log "senha mantida"; return; }
    fi
    while :; do
        read -rs -p "Senha do Steam (não aparece ao digitar): " pw; echo
        [[ -z "${pw}" ]] && { echo "  senha vazia — tente de novo."; continue; }
        read -rs -p "Confirme a senha: " pw2; echo
        [[ "${pw}" == "${pw2}" ]] && break
        echo "  as senhas não conferem — tente de novo."
    done
    # Reescreve o env file preservando o cabeçalho. Valor cru (sem aspas) é o
    # formato lido tanto pelo systemd EnvironmentFile quanto pelo parser do
    # dayzops. Senhas com espaços/aspas nas pontas são casos de borda: edite à
    # mão se for o caso.
    umask 077
    {
        echo "# Senha do Steam usada pelo SteamCMD (lida pelo dayz-update.service)."
        echo "# O servidor DayZ (app 223350) NÃO aceita login anônimo — conta dona do jogo."
        echo "# NÃO versione este arquivo."
        echo "DAYZOPS_STEAM_PASSWORD=${pw}"
    } > /etc/dayzops.env
    chmod 600 /etc/dayzops.env
    chown "${DAYZ_USER}:${DAYZ_USER}" /etc/dayzops.env
    log "senha gravada em /etc/dayzops.env (modo 600)"
}

# Acrescenta clientPort/steamQueryPort ao serverDZ.cfg, sem duplicar. Lê as
# portas do server.yaml para manter consistência. Só roda se o cfg existir
# (ele só é criado pelo 'dayzops apply').
configure_serverdz_cfg() {
    local cfg="${DAYZ_HOME}/server/serverDZ.cfg"
    if [[ ! -f "${cfg}" ]]; then
        log "AVISO: ${cfg} ainda não existe (o servidor não foi baixado?); pulei o ajuste do cfg"
        return
    fi
    local port qport
    port="$(_yaml_value port)";            port="${port:-2302}"
    qport="$(_yaml_value steam_query_port)"; qport="${qport:-27016}"
    if ! grep -qE '^[[:space:]]*clientPort[[:space:]]*=' "${cfg}"; then
        echo "clientPort = ${port};" >> "${cfg}"
        log "serverDZ.cfg: clientPort = ${port}; adicionado"
    fi
    if ! grep -qE '^[[:space:]]*steamQueryPort[[:space:]]*=' "${cfg}"; then
        echo "steamQueryPort = ${qport};" >> "${cfg}"
        log "serverDZ.cfg: steamQueryPort = ${qport}; adicionado"
    fi
    chown "${DAYZ_USER}:${DAYZ_USER}" "${cfg}"
}

print_manual_steps() {
    cat <<EOF

[install] Modo não-interativo. Para finalizar, rode manualmente:
  1. Usuário Steam:   sudo nano ${CONFIG}        (campo steam.username)
  2. Senha do Steam:  sudo nano /etc/dayzops.env (DAYZOPS_STEAM_PASSWORD=, sem #)
  3. Valide:          dayzops validate-config
  4. Baixe o server:  sudo dayzops apply
  5. Ajuste o cfg:    sudo nano ${DAYZ_HOME}/server/serverDZ.cfg
                      (clientPort/steamQueryPort — só existe após o passo 4)
EOF
}

provision_interactive() {
    if [[ -n "${DAYZOPS_NONINTERACTIVE:-}" || ! -t 0 ]]; then
        print_manual_steps
        return
    fi
    echo
    log "--- Configuração do servidor (interativa) ---"
    set_username
    set_password

    if dayzops validate-config >/dev/null 2>&1; then
        log "server.yaml válido"
    else
        log "AVISO: validate-config acusou problemas; revise ${CONFIG} antes do apply"
    fi

    local ans
    read -r -p "Baixar e instalar o servidor DayZ agora? (~2-3 GB) (S/n): " ans || ans=""
    if [[ "${ans}" == "n" || "${ans}" == "N" ]]; then
        log "pulei o 'dayzops apply'. Rode 'sudo dayzops apply' quando quiser."
        return
    fi
    if dayzops apply; then
        configure_serverdz_cfg
        log "servidor instalado e serverDZ.cfg ajustado."
    else
        log "AVISO: 'dayzops apply' falhou (veja a mensagem acima). Corrija e rode de novo."
    fi
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
    provision_interactive
    log "concluído."
}

main "$@"
