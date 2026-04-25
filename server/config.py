from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    stb_portal_url: str
    stb_mac: str
    stb_serial: str = "000000000000"
    stb_lang: str = "en"
    stb_timezone: str = "Europe/London"
    port: int = 8000
