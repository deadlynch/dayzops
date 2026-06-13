#!/usr/bin/env bash
#
# Desinstalador do dayzops. Idempotente (rodar de novo não causa erro).
# Requer root.
#
# Uso:
#   sudo ./scripts/uninstall.sh           Remove serviço, units, pacote e env
#                                          file. PRESERVA ${DAYZ_HOME} (config,
#                                          servidor, mods, backups, estado).
#   sudo ./scripts/uninstall.sh --purge   Tudo acima + APAGA ${DAYZ_HOME} e o
#                                          usuário de sistema (remoção total).
#   --yes / -y                            Não pergunta a confirmação do --purge
#                                          (uso não-interativo / scripts).
#
# Variáveis sobrescrevíveis (use as mesmas da instalação):
#   DAYZ_HOME  (default /srv/dayz)
#   DAYZ_USER  (default dayz)
#
set -euo pipefail

DAYZ_HOME="${DAYZ_HOME:-/srv/dayz}"
DAYZ_USER="${DAYZ_USER:-dayz}"
PURGE=0
ASSUME_YES=0

log() { printf '[uninstall] %s\n' "$*"; }

usage() {
    sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
    case "${arg}" in
        --purge)   PURGE=1 ;;
        --yes|-y)  ASSUME_YES=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "argumento desconhecido: ${arg}" >&2; usage; exit 2 ;;
    esac
done

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "Este desinstalador precisa de root. Rode: sudo ./scripts/uninstall.sh" >&2
        exit 1
    fi
}

stop_services() {
    log "parando e desabilitando serviços/timers"
    systemctl disable --now dayz dayz-update.timer dayz-prune.timer >/dev/null 2>&1 || true
}

remove_units() {
    log "removendo units systemd"
    rm -f /etc/systemd/system/dayz.service \
          /etc/systemd/system/dayz-update.service \
          /etc/systemd/system/dayz-update.timer \
          /etc/systemd/system/dayz-prune.service \
          /etc/systemd/system/dayz-prune.timer
    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl reset-failed >/dev/null 2>&1 || true
}

remove_package() {
    log "removendo o pacote dayzops (pip)"
    if pip uninstall -y dayzops >/dev/null 2>&1 \
       || pip uninstall -y --break-system-packages dayzops >/dev/null 2>&1; then
        log "pacote removido"
    else
        log "pacote dayzops não encontrado via pip (ok)"
    fi
}

remove_env_file() {
    if [[ -f /etc/dayzops.env ]]; then
        log "removendo /etc/dayzops.env"
        rm -f /etc/dayzops.env
    fi
}

purge_data() {
    if [[ "${ASSUME_YES}" -ne 1 ]]; then
        echo
        echo "ATENÇÃO: --purge vai APAGAR PERMANENTEMENTE:"
        echo "  - ${DAYZ_HOME} (config, servidor, mods, backups, estado, cache do SteamCMD)"
        echo "  - o usuário de sistema '${DAYZ_USER}'"
        echo
        read -r -p "Tem certeza? digite 'sim' para confirmar: " answer
        if [[ "${answer}" != "sim" ]]; then
            log "purge cancelado; dados preservados em ${DAYZ_HOME}"
            return
        fi
    fi

    if [[ -d "${DAYZ_HOME}" ]]; then
        log "apagando ${DAYZ_HOME}"
        rm -rf "${DAYZ_HOME}"
    fi

    if id "${DAYZ_USER}" &>/dev/null; then
        log "removendo usuário ${DAYZ_USER}"
        userdel "${DAYZ_USER}" >/dev/null 2>&1 \
            || log "AVISO: não foi possível remover ${DAYZ_USER} (processos ativos?)"
    fi
}

main() {
    require_root
    stop_services
    remove_units
    remove_package
    remove_env_file

    if [[ "${PURGE}" -eq 1 ]]; then
        purge_data
    else
        log "dados em ${DAYZ_HOME} preservados (use --purge para remover tudo)"
    fi

    log "concluído."
}

main "$@"
