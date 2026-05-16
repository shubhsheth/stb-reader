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
    strm_data_dir: str
    vod_sync_interval_hours: int = 24
    vod_sync_request_delay_ms: int = 250
    vod_sync_max_pages: int = 0
    vod_sync_early_stop_pages: int = 3
    vod_sync_full_sync_days: int = 7
    strm_proxy_streams: bool = False
    xtream_username: str = "admin"
    xtream_password: str = "password"
