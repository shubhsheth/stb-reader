from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    stb_portal_url: str
    stb_mac: str
    stb_serial: str = "000000000000"
    stb_lang: str = "en"
    stb_timezone: str = "Europe/London"
    stb_portal_path: str = "stalker_portal/c/portal.php"
    port: int = 8000
    log_level: str = "INFO"

    strm_output_dir: str
    strm_server_base_url: str
    strm_db_path: str = "./library.db"
    strm_sync_interval_hours: int = 6
