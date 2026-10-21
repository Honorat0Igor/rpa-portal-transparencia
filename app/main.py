"""Aplicação FastAPI. Swagger em /docs, OpenAPI em /openapi.json."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.bot.browser import BrowserManager
from app.bot.portal_api import PortalApiClient
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.consulta_service import ConsultaService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    browser = BrowserManager(settings)
    await browser.start()
    api = await PortalApiClient.criar(browser.playwright, settings) if settings.portal_api_key else None
    app.state.browser = browser
    app.state.api_oficial = api
    app.state.service = ConsultaService(browser, settings, api=api)
    yield
    if api:
        await api.aclose()
    await browser.stop()


app = FastAPI(
    title="Robô Portal da Transparência",
    version="1.0.0",
    description=("Coleta dados de Pessoa Física no Portal da Transparência: CPF/NIS pela API oficial "
                 "(quando PORTAL_API_KEY está configurada) e nomes via RPA com Playwright."),
    lifespan=lifespan,
)
app.include_router(router)
