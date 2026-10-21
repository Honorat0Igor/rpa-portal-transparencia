"""Configuração centralizada via variáveis de ambiente (12-factor)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Portal
    portal_base_url: str = "https://portaldatransparencia.gov.br"

    # API oficial (CPF/NIS). Sem chave, essas consultas também usam o navegador.
    portal_api_url: str = "https://api.portaldatransparencia.gov.br/api-de-dados"
    portal_api_key: str | None = None
    portal_api_timeout_s: float = 30
    portal_api_max_paginas: int = 3  # páginas por benefício (cada página tem até 15 registros)

    # Navegador
    headless: bool = True
    chromium_executable_path: str | None = None  # opcional: Chrome/Chromium já instalado
    max_concurrent_bots: int = 3
    navigation_timeout_ms: int = 30_000
    search_timeout_ms: int = 20_000
    total_timeout_s: float = 120

    # API
    api_key: str | None = None  # se definida, exige header X-API-Key

    # Saída
    save_output_files: bool = True
    output_dir: str = "output"
    timezone: str = "America/Sao_Paulo"

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
