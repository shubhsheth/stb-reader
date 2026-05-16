import json
import pytest
from click.testing import CliRunner
from stb_reader.cli.main import main
from stb_reader.cli import config as config_mod


@pytest.fixture(autouse=True)
def tmp_config(tmp_path, monkeypatch):
    cfg = tmp_path / ".stb" / "config"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg)
    return cfg


def test_save_and_load_config(tmp_config):
    config_mod.save_config({"url": "http://portal.test", "mac": "AA:BB:CC:DD:EE:FF"})
    data = config_mod.load_config()
    assert data["url"] == "http://portal.test"
    assert data["mac"] == "AA:BB:CC:DD:EE:FF"


def test_load_config_missing_raises(tmp_config):
    from click import ClickException
    with pytest.raises(ClickException, match="stb init"):
        config_mod.load_config()


_INIT_DEFAULTS = "http://portal.test\n\nAA:BB:CC:DD:EE:FF\n\n\n\n\n"


def test_init_command_writes_config(tmp_config):
    result = CliRunner().invoke(main, ["init"], input=_INIT_DEFAULTS)
    assert result.exit_code == 0
    data = json.loads(tmp_config.read_text())
    assert data["url"] == "http://portal.test"
    assert data["mac"] == "AA:BB:CC:DD:EE:FF"
    assert data["serial"] == "000000000000"
    assert data["lang"] == "en"
    assert data["timezone"] == "Europe/London"
    assert data["portal_path"] == "stalker_portal/c/portal.php"
    assert "port" not in data


def test_init_with_port(tmp_config):
    CliRunner().invoke(main, ["init"], input="http://portal.test\n8080\nAA:BB:CC:DD:EE:FF\n\n\n\n\n")
    data = json.loads(tmp_config.read_text())
    assert data["port"] == "8080"


def test_init_custom_portal_path(tmp_config):
    CliRunner().invoke(main, ["init"], input="http://portal.test\n\nAA:BB:CC:DD:EE:FF\n\n\n\nstalker_portal/server/load.php\n")
    data = json.loads(tmp_config.read_text())
    assert data["portal_path"] == "stalker_portal/server/load.php"


def test_init_strips_trailing_slash(tmp_config):
    CliRunner().invoke(main, ["init"], input="http://portal.test/\n\nAA:BB:CC:DD:EE:FF\n\n\n\n\n")
    data = json.loads(tmp_config.read_text())
    assert data["url"] == "http://portal.test"


def test_get_client_appends_port(tmp_config, monkeypatch):
    config_mod.save_config({"url": "http://portal.test", "port": "8080", "mac": "AA:BB:CC:DD:EE:FF"})
    captured = {}

    def fake_init(self, base_url, mac, **kwargs):
        captured["base_url"] = base_url

    monkeypatch.setattr("stb_reader.client.STBClient.__init__", fake_init)
    monkeypatch.setattr("stb_reader.client.STBClient.authenticate", lambda self: None)
    config_mod.get_client()
    assert captured["base_url"] == "http://portal.test:8080"
