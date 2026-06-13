# Commit final — divergências #12, #14 e ownership

Suite: **125 passed** (104 → 125, +21 testes novos).

## Arquivos modificados / novos

| Arquivo | Destino no repo | Status | Resumo |
|---|---|---|---|
| `fsperm.py` | `src/dayzops/fsperm.py` | **NOVO** | Helper centralizado de chown ao service_user |
| `keys.py` | `src/dayzops/keys.py` | reescrito | Sync incremental + chown nas escritas |
| `mods.py` | `src/dayzops/mods.py` | edit | Symlinks chowned via lchown |
| `steamcmd.py` | `src/dayzops/steamcmd.py` | edit | Workshop dir + symlink + conteúdo recursivo chowned |
| `apply.py` | `src/dayzops/apply.py` | edit | ExecStart Bohemia + profiles/ chowned + install_dir chown defensivo |
| `app.py` | `src/dayzops/app.py` | edit | Propaga service_user pros componentes |
| `install.sh` | `scripts/install.sh` | edit | Cria `server/profiles/` |
| `server.yaml` | `examples/server.yaml` | edit | Novos opcionais documentados |
| `test_fsperm.py` | `tests/test_fsperm.py` | **NOVO** | 8 testes do helper |
| `test_keys.py` | `tests/test_keys.py` | reescrito | 12 testes do novo paradigma |
| `test_apply.py` | `tests/test_apply.py` | edit | +7 testes (Bohemia flags, profiles, propagação) |

## Commits sugeridos (3 commits separados)

### Commit 1 — divergência #12: ExecStart Bohemia + profiles/

```
feat(systemd): inclui flags Bohemia no ExecStart e cria profiles/

Divergência #12 — ExecStart sem flags recomendadas pela Bohemia
(community.bistudio.com/wiki/DayZ:Server_Configuration) deixava o
BattlEye em path default e logs em $HOME/.local/share/DayZ Other Profiles/
(path literal observado nos logs em produção).

Hardcoded no template:
  -BEpath={install_dir}/battleye
  -profiles={install_dir}/{instance.profile}
  -doLogs -adminLog -netLog -freezeCheck

Configuráveis via server.yaml (omitir = não passar):
  server.cpu_count       → -cpuCount=N
  server.limit_fps       → -limitFPS=N
  server.file_patching   → -filePatching
  server.extra_args      → lista
  paths.storage_dir      → -storage=path

_ensure_runtime_dirs() cria a pasta profile idempotentemente.
install.sh passa a criar server/profiles/ na instalação inicial.

Refs: divergência #12.
```

Arquivos: `apply.py` (parcial — build_exec_start + _ensure_runtime_dirs),
`install.sh`, `server.yaml`, `test_apply.py` (parcial — testes #12).

### Commit 2 — divergência #14: keys.sync incremental (substitui ADR-0004)

```
fix(keys): substitui rmtree+rebuild por sync incremental por origem

Divergência #14 — KeyManager.rebuild() chamava shutil.rmtree(keys_dir)
toda vez, eliminando a dayz.bikey (Bohemia, vem com o server base) e
qualquer key colocada manualmente pelo operador. Resultado em produção:
kick 118 "Server installation is corrupt. Missing PBO (dta\bin.pbo)"
toda vez que apply rodava.

Nova abordagem (substitui ADR-0004):

  - state.installed_keys registra qual mod originou cada key copiada.
  - sync(): copia novas, atualiza alteradas (conteúdo), remove SÓ keys
    de mods que saíram do server.yaml.
  - Keys NÃO REGISTRADAS na pasta (órfãs) são SEMPRE preservadas —
    dayz.bikey, keys manuais, keys de mods locais.
  - Conflito de nome (mod traz key com mesmo nome de órfã): NÃO sobrescreve,
    operador decide manualmente.

rebuild() vira alias backward-compat de sync().

Refs: divergência #14, substitui ADR-0004.
```

Arquivos: `keys.py` (reescrito), `app.py` (parcial — passa store/service_user
ao KeyManager, mod_dirs_with_id), `apply.py` (parcial — chama keys.sync),
`test_keys.py` (reescrito).

### Commit 3 — ownership: chown único ponto via fsperm

```
fix(fsperm): garante service_user dono de tudo que dayzops cria

Vimos em produção: dayzops apply rodando via sudo deixava arquivos
root:root pra trás (symlinks @Mod, keys/, mpmissions/regular.namalsk).
O servidor roda como dayz e não conseguia ler/escrever neles.

Novo módulo fsperm centraliza chown ao service_user:
  - chown_path: single-shot, usa lchown (não segue symlink — importante
    pros links de mods).
  - chown_recursive: walk + lchown em cada entry.
  - No-op fora de root (dev/CI), warning sem raise em OSError.

Pontos atualizados:
  - keys.py: keys_dir + cada key copiada/atualizada.
  - mods.py: server_dir + cada symlink criado/atualizado (lchown).
  - steamcmd.py: workshop_dir + symlink + conteúdo do mod (recursivo).
  - apply.py: install_dir após install_or_update_server (defensivo,
    cobre quando o sudo -u wrap do steamcmd falha por ambiente);
    profile_path em _ensure_runtime_dirs.
  - app.py: propaga service_user pros componentes via build_services.

Testes: test_fsperm.py (8 testes, mocking lchown), test_apply
test_modsync_and_keys_receive_service_user (regressão arquitetural).

Refs: divergência #14 estendida.
```

Arquivos: `fsperm.py` (novo), `keys.py` (parte — chown), `mods.py`,
`steamcmd.py`, `apply.py` (parte — chown), `app.py` (parte — propagação),
`test_fsperm.py` (novo), `test_apply.py` (parte — regressão).

> **Nota:** os 3 commits acima compartilham arquivos. Se preferir simplicidade,
> faça **um commit só** com mensagem combinada — todas as mudanças se reforçam
> e foram desenvolvidas juntas hoje.

## Aplicação no repo

```bash
cd ~/dayzops

cp /caminho/commit-final/fsperm.py     src/dayzops/fsperm.py    # NOVO
cp /caminho/commit-final/keys.py       src/dayzops/keys.py
cp /caminho/commit-final/mods.py       src/dayzops/mods.py
cp /caminho/commit-final/steamcmd.py   src/dayzops/steamcmd.py
cp /caminho/commit-final/apply.py      src/dayzops/apply.py
cp /caminho/commit-final/app.py        src/dayzops/app.py
cp /caminho/commit-final/install.sh    scripts/install.sh
cp /caminho/commit-final/server.yaml   examples/server.yaml
cp /caminho/commit-final/test_fsperm.py tests/test_fsperm.py   # NOVO
cp /caminho/commit-final/test_keys.py   tests/test_keys.py
cp /caminho/commit-final/test_apply.py  tests/test_apply.py

python -m pytest -q   # 125 passed esperado

git add src/dayzops/fsperm.py src/dayzops/keys.py src/dayzops/mods.py \
        src/dayzops/steamcmd.py src/dayzops/apply.py src/dayzops/app.py \
        scripts/install.sh examples/server.yaml \
        tests/test_fsperm.py tests/test_keys.py tests/test_apply.py

# Decide: 1 commit consolidado ou 3 separados conforme acima
git commit -m "..."
git push
```

## Validação pós-deploy no vostro-srv

```bash
cd ~/dayzops && git pull && sudo pip install -e . --break-system-packages

# 1. Apply regenera unit com flags Bohemia
sudo dayzops apply
grep ExecStart /etc/systemd/system/dayz.service
# espera-se -BEpath, -profiles, -doLogs, -adminLog, -netLog, -freezeCheck

# 2. dayz.bikey continua viva após apply (era o bug real do dia)
ls -la /srv/dayz/server/keys/dayz.bikey
# existe + dono dayz:dayz

# 3. State registra só keys de mods, não órfãs
cat /srv/dayz/state/installed-keys.json
# lista Jacob_Mango_V3.bikey e sumrak.bikey; dayz.bikey NÃO está aqui

# 4. Todos os symlinks @Mod com dono dayz:dayz
ls -la /srv/dayz/server/ | grep -E "@|keys"
# tudo dayz:dayz, sem root:root

# 5. Restart e conexão limpa
sudo systemctl daemon-reload && sudo systemctl restart dayz
journalctl -u dayz -f
# cliente conecta sem kick 118
```

## Pendente fora deste commit (não bloqueante)

- **Divergência #13** (SteamCMD exit 0x626 tratado como fatal) — patch separado
- **ADR-0004 revisão**: documentar `docs/adr/0004-keys-sync.md` substituindo a estratégia destrutiva
- **Lotes anteriores não-commitados**: swapfix, applyfix, ci.yml, permfix, steamauth
- **mpmissions custom**: `apply` poderia detectar `mpmissions/` populada e chownar (cenário do regular.namalsk de hoje); por enquanto, o `chown_recursive(install_dir)` defensivo após install do server cobre nas instalações novas
