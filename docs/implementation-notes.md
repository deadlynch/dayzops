# Notas de Implementação: divergências ADR ↔ código

Este documento registra os pontos onde a implementação refinou, ajustou ou
estendeu o que os ADRs originais descreviam. O objetivo não é apontar erro nos
ADRs — eles capturaram bem a intenção — mas manter o registro honesto entre o
design recebido e o código que ele virou, para quem ler depois.

Cada item traz: o que o ADR dizia, o que o código faz, por quê, e a ação
recomendada.

## 1. Lock global: estado do flock, não presença de arquivo (ADR-0009)

**ADR:** "Se o lock existe → operação abortada."

**Código:** o arquivo `/run/dayzops.lock` fica permanente; a exclusão vem do
estado do `fcntl.flock`, não da existência do arquivo. "Lock ocupado → aborta".

**Por quê:** lock por presença de arquivo fica órfão se o processo morre
(crash, `kill -9`). O `flock` é liberado pelo kernel ao fechar o fd, então
não há lock preso. Remover o arquivo no fim introduziria a race clássica de
`flock` + `unlink`.

**Ação recomendada:** atualizar o texto do ADR-0009 para descrever a semântica
de `flock`, mantendo a decisão registrada.

## 2. Nome do symlink de mod é opcional (ADR-0007)

**ADR:** o exemplo de config lista mods só por `id`.

**Código:** cada mod aceita um `name` opcional; sem ele, o symlink usa
`@<id>` como default determinístico.

**Por quê:** o symlink precisa de um nome de pasta (`@CF`), mas o ADR só
modelava o `id`. O default mantém o exemplo válido sem obrigar o campo.

**Ação recomendada:** documentar o campo `name` opcional no ADR-0007 e no
exemplo de configuração.

## 3. Validação e health check: escopo do que foi checado (ADR-0006)

**ADR:** passos "Validate" e "Health Check" no workflow, sem detalhar o quê.

**Código:** `validate` confere presença de binário, config e conteúdo dos
mods; `health_check` faz polling de `systemctl is-active` com retries. Uma
query A2S/UDP de verdade ficou como hook opcional, não habilitado por padrão.

**Por quê:** o nível de processo é o sinal confiável; detectar "porta UDP
aberta" por socket é pouco confiável e mereceria um protocolo de query.

**Ação recomendada:** se a query A2S for desejada, abrir um ADR específico
para o protocolo de health check.

## 4. Senha do Steam fora do config (sem ADR)

**Código:** a senha do Steam é lida apenas de `DAYZOPS_STEAM_PASSWORD`,
nunca do `server.yaml`, e é redigida (`***`) nos logs.

**Por quê:** o `server.yaml` é versionável e compartilhável; segredo não pode
morar nele. Em produção a variável viria de um cofre de credenciais.

**Ação recomendada:** registrar essa decisão de segurança como um ADR novo
(ex.: ADR-0011: Tratamento de Credenciais).

## 5. Extração de backup defendida contra path traversal (ADR-0005)

**Código:** `restore` valida que cada membro do `.tar.gz` resolve para dentro
do diretório de destino antes de extrair (defesa contra "tarbomb"), além de
usar `filter="data"` quando disponível.

**Por quê:** um arquivo malicioso poderia escrever fora do destino. Não é uma
funcionalidade, é um requisito de segurança que o ADR não citava.

**Ação recomendada:** acrescentar a nota de segurança ao ADR-0005.

## 6. Edição de config perde comentários (sem ADR)

**Código:** `mod add/remove` reserializa o `server.yaml` via
`yaml.safe_dump`, que não preserva comentários nem o estilo original.

**Por quê:** decisão de simplicidade. Preservar exigiria uma lib com round-trip
de comentários (`ruamel.yaml`).

**Ação recomendada:** decidir entre aceitar o trade-off ou trocar a lib, e
registrar num ADR novo. Hoje é a divergência mais visível para o usuário final.

## 7. Layout do Workshop abstraído (ADR-0003)

**ADR/Código:** o conteúdo do mod é tratado como `workshop/<id>`. O SteamCMD,
na prática, baixa para `workshop/content/221100/<id>/`.

**Por quê:** seguir a abstração do ADR mantém o código desacoplado do layout
interno do SteamCMD.

**Ação recomendada:** ao integrar o download real, reconciliar o caminho (ex.:
um symlink ou normalização) e anotar onde a abstração encosta na realidade.

## 8. Nome de arquivo de backup com resolução de segundos

**Código:** o nome é `dayz-backup-<YYYYMMDDTHHMMSSZ>.tar.gz`.

**Consequência:** dois backups criados no **mesmo segundo** colidem (o segundo
sobrescreve o primeiro). Sem impacto no uso real (backups são espaçados por
horas), mas é uma aresta.

**Ação recomendada:** se um dia incomodar, acrescentar milissegundos ou um
sufixo curto ao nome.

## 9. Senha do Steam via EnvironmentFile

**Código:** o `dayz-update.service` referencia `EnvironmentFile=-/etc/dayzops.env`
(opcional), e o instalador cria esse arquivo protegido (mode 600). A senha
nunca entra no `server.yaml`.

**Ação recomendada:** em ambiente corporativo, popular `/etc/dayzops.env` a
partir de um cofre (ex.: Keeper) em vez de editar à mão. Ver ADR sugerido no
item 4.

## 10. managed_files / managed_dirs não implementados

**Docs antigas:** `architecture.md` e exemplos citavam deploy declarativo de
arquivos (`managed_files`, `managed_dirs`).

**Código:** não implementado. As docs foram ajustadas para marcá-lo como
trabalho futuro.

**Ação recomendada:** se for implementar, abrir um ADR para o modelo de
deploy de recursos gerenciados.

## 11. Inventário de estado em JSON (não YAML)

**Docs antigas:** `architecture.md` listava arquivos de estado com extensão
`.yaml`.

**Código:** os inventários são JSON (`installed-mods.json`, etc.), gravados
atomicamente. As docs foram corrigidas.
