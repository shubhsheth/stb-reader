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


def test_init_command_writes_config(tmp_config):
    runner = CliRunner()
    result = runner.invoke(main, ["init"], input="http://portal.test\nAA:BB:CC:DD:EE:FF\n")
    assert result.exit_code == 0
    data = json.loads(tmp_config.read_text())
    assert data["url"] == "http://portal.test"
    assert data["mac"] == "AA:BB:CC:DD:EE:FF"


def test_init_strips_trailing_slash(tmp_config):
    runner = CliRunner()
    runner.invoke(main, ["init"], input="http://portal.test/\nAA:BB:CC:DD:EE:FF\n")
    data = json.loads(tmp_config.read_text())
    assert data["url"] == "http://portal.test"
