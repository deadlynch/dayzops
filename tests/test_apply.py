import types

from dayzops import app, apply


def _result(returncode=0, stdout="Success"):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def _svc(tmp_path, *, server_installed=True, mod_content=True, steam_runner=None):
    server = tmp_path / "server"
    workshop = tmp_path / "workshop"
    server.mkdir(parents=True)
    if server_installed:
        (server / "DayZServer").write_text("binario")
    workshop.mkdir(parents=True, exist_ok=True)
    if mod_content:
        (workshop / "1559212036").mkdir()
    cfg = {
        "server": {"name": "T", "map": "chernarus", "port": 2302},
        "steam": {"username": "alice"},
        "paths": {
            "install_dir": str(server),
            "workshop_dir": str(workshop),
            "mods_dir": str(tmp_path / "mods"),
            "backups_dir": str(tmp_path / "backups"),
            "state_dir": str(tmp_path / "state"),
        },
        "mods": [{"id": 1559212036, "name": "CF"}],
        "servermods": [],
    }
    return app.build_services(cfg, steam_runner=steam_runner or (lambda c: _result()),
                              control_runner=lambda c: _result())


def test_plan_lists_mods_and_units(tmp_path):
    svc = _svc(tmp_path)
    plan = apply.build_plan(svc, units_dir=tmp_path / "units")
    kinds = {(c.resource, c.action) for c in plan.changes}
    assert ("mod", "create") in kinds       # @CF ainda não existe
    assert ("unit", "create") in kinds      # nenhuma unit em disco
    assert not plan.empty


def test_plan_flags_missing_server(tmp_path):
    svc = _svc(tmp_path, server_installed=False)
    plan = apply.build_plan(svc, units_dir=tmp_path / "units")
    assert any(c.resource == "server" for c in plan.changes)


def test_dry_run_changes_nothing(tmp_path):
    svc = _svc(tmp_path)
    units = tmp_path / "units"
    plan = apply.run_apply(svc, units_dir=units, dry_run=True,
                           lock_file=tmp_path / "dayzops.lock")
    assert not plan.empty
    # nada foi criado
    assert not (tmp_path / "server" / "@CF").exists()
    assert not units.exists()


def test_apply_converges(tmp_path):
    svc = _svc(tmp_path)
    units = tmp_path / "units"
    apply.run_apply(svc, units_dir=units, lock_file=tmp_path / "dayzops.lock")

    assert (tmp_path / "server" / "@CF").is_symlink()
    assert (units / "dayz.service").exists()
    assert svc.store.installed_mods() == [{"id": 1559212036, "name": "@CF"}]


def test_plan_flags_missing_mod_content(tmp_path):
    svc = _svc(tmp_path, mod_content=False)
    plan = apply.build_plan(svc, units_dir=tmp_path / "units")
    assert ("mod", "download") in {(c.resource, c.action) for c in plan.changes}


def test_apply_downloads_missing_mod_content(tmp_path):
    calls = []
    svc = _svc(tmp_path, mod_content=False,
               steam_runner=lambda c: (calls.append(c), _result())[1])
    apply.run_apply(svc, units_dir=tmp_path / "units",
                    lock_file=tmp_path / "dayzops.lock")
    assert any("+workshop_download_item" in c for c in calls)


def test_plan_no_download_when_content_present(tmp_path):
    svc = _svc(tmp_path, mod_content=True)
    plan = apply.build_plan(svc, units_dir=tmp_path / "units")
    assert ("mod", "download") not in {(c.resource, c.action) for c in plan.changes}


def test_apply_is_idempotent(tmp_path):
    svc = _svc(tmp_path)
    units = tmp_path / "units"
    lock = tmp_path / "dayzops.lock"

    apply.run_apply(svc, units_dir=units, lock_file=lock)
    # segunda vez: nada divergiu -> plano vazio
    second = apply.run_apply(svc, units_dir=units, lock_file=lock)
    assert second.empty


def test_apply_reconverges_after_drift(tmp_path):
    svc = _svc(tmp_path)
    units = tmp_path / "units"
    lock = tmp_path / "dayzops.lock"
    apply.run_apply(svc, units_dir=units, lock_file=lock)

    # drift: alguém apagou um symlink na mão
    (tmp_path / "server" / "@CF").unlink()

    plan = apply.run_apply(svc, units_dir=units, lock_file=lock)
    assert any(c.resource == "mod" and c.action == "create" for c in plan.changes)
    assert (tmp_path / "server" / "@CF").is_symlink()  # reconvergido


# --- divergência #12: flags Bohemia no ExecStart ---

def test_exec_start_includes_bohemia_required_flags(tmp_path):
    """Bohemia wiki (DayZ:Server_Configuration) lista estas flags como
    recomendadas; sem -BEpath/-profiles o BattlEye handshake falha e logs
    caem em path bagunçado. Vimos isso em ambiente real (divergência #12).
    """
    svc = _svc(tmp_path)
    cmd = apply.build_exec_start(svc)
    assert "-BEpath=" in cmd
    assert "-profiles=" in cmd
    assert "-doLogs" in cmd
    assert "-adminLog" in cmd
    assert "-netLog" in cmd
    assert "-freezeCheck" in cmd


def test_exec_start_profiles_path_uses_instance_profile(tmp_path):
    """instance.profile customizado é refletido no -profiles= do ExecStart."""
    svc = _svc(tmp_path)
    svc.config["instance"] = {"profile": "myprofile", "config": "serverDZ.cfg"}
    cmd = apply.build_exec_start(svc)
    assert f"-profiles={svc.install_dir}/myprofile" in cmd


def test_exec_start_omits_optional_flags_by_default(tmp_path):
    """Sem campos opt no server.yaml, ExecStart não inclui as flags opcionais."""
    svc = _svc(tmp_path)
    cmd = apply.build_exec_start(svc)
    assert "-cpuCount=" not in cmd
    assert "-limitFPS=" not in cmd
    assert "-filePatching" not in cmd
    assert "-storage=" not in cmd


def test_exec_start_includes_optional_yaml_flags(tmp_path):
    """server.cpu_count / limit_fps / file_patching / extra_args / storage_dir
    aparecem no ExecStart quando configurados.
    """
    svc = _svc(tmp_path)
    svc.config["server"]["cpu_count"] = 8
    svc.config["server"]["limit_fps"] = 100
    svc.config["server"]["file_patching"] = True
    svc.config["server"]["extra_args"] = ["-cfgGameplayFile=foo.json"]
    svc.config["paths"]["storage_dir"] = "/srv/dayz/storage"
    cmd = apply.build_exec_start(svc)
    assert "-cpuCount=8" in cmd
    assert "-limitFPS=100" in cmd
    assert "-filePatching" in cmd
    assert "-cfgGameplayFile=foo.json" in cmd
    assert "-storage=/srv/dayz/storage" in cmd


def test_apply_creates_profiles_dir_if_missing(tmp_path):
    """Servers existentes (pré-fix install.sh) podem não ter profiles/. O
    apply deve criar idempotentemente — senão ExecStart aponta pra dir
    inexistente e servidor falha a escrever logs.
    """
    svc = _svc(tmp_path)
    profiles = tmp_path / "server" / "profiles"
    assert not profiles.exists()  # estado inicial: ausente
    apply.run_apply(svc, units_dir=tmp_path / "units", lock_file=tmp_path / "lock")
    assert profiles.is_dir()


def test_apply_respects_custom_profile_name(tmp_path):
    """instance.profile customizado leva _ensure_runtime_dirs a criar a pasta certa."""
    svc = _svc(tmp_path)
    svc.config["instance"] = {"profile": "custom_prof", "config": "serverDZ.cfg"}
    apply.run_apply(svc, units_dir=tmp_path / "units", lock_file=tmp_path / "lock")
    assert (tmp_path / "server" / "custom_prof").is_dir()


# --- divergência #14 estendida: propagação de service_user ---

def test_modsync_and_keys_receive_service_user(tmp_path):
    """build_services deve propagar service_user pros componentes que escrevem
    no fs do servidor. Sem isso, chown vira no-op silencioso e regredimos
    pro bug original de arquivos root:root.
    """
    svc = _svc(tmp_path)
    # Default no helper: service.user="dayz" via _get default
    assert svc.modsync.service_user == svc.service_user
    assert svc.keys.service_user == svc.service_user
    # Sanity: bate com o config (default "dayz")
    assert svc.service_user == "dayz"
