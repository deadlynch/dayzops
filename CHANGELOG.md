# Changelog

Todas as mudanças relevantes do projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/) e o projeto
adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.9.0] - 2026-06-12

Primeira versão funcional. A arquitetura que existia apenas como ADRs foi
implementada por inteiro: o workflow atômico de update do ADR-0006 roda com
código real de ponta a ponta, e a superfície de comandos do README está
completa.

### Added

- Logging estruturado em stderr (`logger.py`), capturado pelo journald sob
  systemd; nível configurável via `DAYZOPS_LOG_LEVEL`.
- Lock global por `fcntl.flock` (`lock.py`) garantindo exclusão mútua entre
  operações críticas (ADR-0009).
- Inventário de estado persistido com escrita atômica (`state.py`, ADR-0010).
- Wrapper do SteamCMD para instalar/atualizar servidor e baixar mods
  (`steamcmd.py`), com a senha lida só de `DAYZOPS_STEAM_PASSWORD` e redigida
  nos logs.
- Backup e restauração em `.tar.gz` com extração defendida contra path
  traversal (`backup.py`, ADR-0005).
- Gestão de mods por symlink, idempotente, com geração de parâmetros de
  startup preservando a ordem (`mods.py`, ADR-0003/0007/0008).
- Geração de units systemd e controle do serviço via `systemctl`
  (`systemd.py`, ADR-0002).
- Rebuild completo do diretório de keys (`keys.py`, ADR-0004).
- Validação pré-start (`verify.py`) e health check com retries (`health.py`),
  completando o workflow do ADR-0006.
- Orquestração atômica de update com rollback automático (`ops.py`, ADR-0006).
- Reconciliação declarativa `dayzops apply`, com `--dry-run`, idempotência e
  detecção de drift (`apply.py`).
- Raiz de composição que monta todos os colaboradores a partir do config
  (`app.py`).
- Comandos da CLI: `status`, `update`, `backup`, `rollback`, `start`, `stop`,
  `restart`, `apply` e o grupo `mod` (`list`/`add`/`remove`).
- Suíte de testes cobrindo todos os módulos.

### Changed

- `validate-config` agora carrega **e** valida o conteúdo (presença de campos
  obrigatórios + tipo/valor), em vez de só verificar o parse do YAML.
- `DEFAULT_CONFIG` alinhado à documentacao (`/srv/dayz/config/server.yaml`);
  caminho sobrescrevível com `-c/--config`.
- CLI migrada para `argparse` com subcomandos.

### Fixed

- `validate-config` não executava a validação de campos obrigatórios (a
  função existia mas nunca era chamada).
- `python -m dayzops` descartava o código de retorno de `main()`, sempre
  saindo com 0 e mascarando falhas em scripts/CI.

### Notes

- Divergências entre os ADRs e a implementação final estão registradas em
  `docs/implementation-notes.md`.
- Pendente para a 1.0.0: instalador (`install.sh` + `bin/dayzops`) e `prune`
  de backup no agendamento.

## [0.1.0]

### Added

- Arquitetura inicial e ADR-0001 a ADR-0010.
- Estrutura do projeto, documentação de instalação e operações, exemplo de
  configuração.
