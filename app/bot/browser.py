"""Gerenciamento do navegador para execuções simultâneas.

Estratégia: UM processo Chromium compartilhado + UM BrowserContext isolado por
consulta (cookies/sessão independentes). Um semáforo limita quantos robôs rodam
ao mesmo tempo, protegendo memória/CPU e evitando bloqueio pelo portal.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from app.core.config import Settings

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


class BrowserManager:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._semaforo = asyncio.Semaphore(settings.max_concurrent_bots)
        self._lock = asyncio.Lock()
        self._lock_inicio = asyncio.Lock()
        self._ultimo_inicio = float("-inf")
        self._em_execucao = 0

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        await self._lancar()

    async def _lancar(self) -> None:
        self._browser = await self._playwright.chromium.launch(
            headless=self._settings.headless,
            executable_path=self._settings.chromium_executable_path or None,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        logger.info("Chromium iniciado (headless=%s)", self._settings.headless)

    async def _garantir_browser(self) -> Browser:
        # Reinicia o Chromium se ele tiver caído (resiliência)
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                logger.warning("Navegador desconectado; reiniciando")
                await self._lancar()
        return self._browser

    async def _aguardar_intervalo(self) -> None:
        # Espaça o início dos robôs: rajadas simultâneas do mesmo IP disparam o CAPTCHA do portal
        async with self._lock_inicio:
            relogio = asyncio.get_running_loop()
            espera = self._ultimo_inicio + self._settings.bot_start_interval_s - relogio.time()
            if espera > 0:
                await asyncio.sleep(espera)
            self._ultimo_inicio = relogio.time()

    async def stop(self) -> None:
        # No Windows, o Ctrl+C pode derrubar o driver antes do desligamento; não há o que fechar
        try:
            if self._browser:
                await self._browser.close()
        except Exception as exc:
            logger.debug("Navegador já encerrado: %s", exc)
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as exc:
            logger.debug("Playwright já encerrado: %s", exc)

    @property
    def playwright(self) -> Playwright:
        """Instância do Playwright, compartilhada com o cliente da API oficial."""
        return self._playwright

    @property
    def em_execucao(self) -> int:
        return self._em_execucao

    @property
    def conectado(self) -> bool:
        return bool(self._browser and self._browser.is_connected())

    @asynccontextmanager
    async def contexto(self) -> AsyncIterator[BrowserContext]:
        async with self._semaforo:
            await self._aguardar_intervalo()
            browser = await self._garantir_browser()
            ctx = await self._browser.new_context(
                locale="pt-BR",
                timezone_id=self._settings.timezone,
                user_agent=USER_AGENT,
                viewport={"width": 1366, "height": 900},
                bypass_csp=True,
            )
            ctx.set_default_timeout(self._settings.navigation_timeout_ms)
            self._em_execucao += 1
            try:
                yield ctx
            finally:
                self._em_execucao -= 1
                await ctx.close()
