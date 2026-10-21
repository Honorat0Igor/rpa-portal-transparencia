"""Robô de coleta no Portal da Transparência (Playwright async).

Fluxo:
 1. Abre a consulta de Pessoa Física com termo (+ filtro opcional)
 2. Aguarda resultado; 0 resultados -> NenhumResultadoError
 3. Abre o primeiro registro (tela "Panorama da relação da pessoa com o Governo Federal")
 4. Expande seções, coleta dados e captura evidência (PNG -> Base64)
 5. Para cada benefício ("Detalhar"), abre o detalhe e coleta as tabelas
"""
import base64
import logging
from urllib.parse import urlencode, urljoin

from playwright.async_api import BrowserContext, Page
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from app.bot import parsers
from app.bot import selectors as sel
from app.bot.exceptions import (BloqueioAntiBotError, BotError, NenhumResultadoError, PortalIndisponivelError,
                                TempoEsgotadoError)
from app.core.config import Settings
from app.schemas import Beneficio, DadosPessoa

logger = logging.getLogger(__name__)


class PortalTransparenciaScraper:
    def __init__(self, context: BrowserContext, settings: Settings):
        self._context = context
        self._settings = settings
        self._base = settings.portal_base_url.rstrip("/")

    # ------------------------------------------------------------------ API
    async def consultar(self, termo: str, filtro_social: bool) -> tuple[DadosPessoa, str]:
        page = await self._context.new_page()
        try:
            url_pessoa = await self._buscar(page, termo, filtro_social)
            dados = await self._coletar_panorama(page, url_pessoa)
            evidencia = await self._capturar_evidencia(page)
            dados.beneficios = await self._coletar_beneficios(page)
            return dados, evidencia
        except BotError as exc:
            exc.evidencia_base64 = exc.evidencia_base64 or await self._evidencia_segura(page)
            raise
        finally:
            await page.close()

    # --------------------------------------------------------------- etapas
    async def _buscar(self, page: Page, termo: str, filtro_social: bool) -> str:
        params = {"termo": termo, "pagina": 1, "tamanhoPagina": 10}
        if filtro_social:
            params[sel.FILTRO_BENEFICIARIO_PARAM] = "true"
        await self._navegar(page, f"{self._base}{sel.PATH_BUSCA_PF}?{urlencode(params)}")
        await self._aceitar_cookies(page)

        try:
            await page.wait_for_function(sel.JS_BUSCA_CONCLUIDA, timeout=self._settings.search_timeout_ms)
        except PlaywrightTimeout as exc:
            await self._verificar_bloqueio(page)
            raise TempoEsgotadoError("Busca não retornou dentro do tempo limite") from exc

        total = parsers.parse_total_resultados(await self._texto(page, sel.BUSCA_CONTADOR))
        links = page.locator(sel.BUSCA_LINK_RESULTADO)
        if total == 0 or await links.count() == 0:
            raise NenhumResultadoError(f"0 resultados para '{termo}'")

        logger.info("Busca retornou %s resultado(s); abrindo o primeiro", total)
        href = await links.first.get_attribute("href")
        return urljoin(self._base + "/", href)

    async def _coletar_panorama(self, page: Page, url: str) -> DadosPessoa:
        await self._navegar(page, url)
        await self._aceitar_cookies(page)
        try:
            await page.wait_for_selector(sel.PANORAMA_DADOS, timeout=self._settings.navigation_timeout_ms)
        except PlaywrightTimeout as exc:
            await self._verificar_bloqueio(page)
            raise TempoEsgotadoError("Tela de panorama não carregou") from exc

        await self._expandir_secoes(page)
        campos = parsers.normalizar_campos(await page.evaluate(sel.JS_DADOS_ROTULADOS, sel.PANORAMA_DADOS))
        tabelas = await page.evaluate(sel.JS_TABELAS, sel.AREA_PRINCIPAL)

        return DadosPessoa(
            nome=campos.get("nome"),
            cpf=campos.get("cpf"),
            localidade=campos.get("localidade"),
            url_panorama=url,
            dados_panorama=campos,
            recebimentos_recursos=parsers.tabelas_para_registros(tabelas),
        )

    async def _coletar_beneficios(self, page: Page) -> list[Beneficio]:
        links = await page.evaluate(sel.JS_LINKS_BENEFICIOS, sel.AREA_PRINCIPAL)
        vistos, beneficios = set(), []
        for link in links:
            if link["href"] in vistos:
                continue
            vistos.add(link["href"])
            beneficios.append(await self._coletar_detalhe(link))
        logger.info("%d benefício(s) detalhado(s)", len(beneficios))
        return beneficios

    async def _coletar_detalhe(self, link: dict) -> Beneficio:
        beneficio = Beneficio(
            programa=parsers.identificar_programa(link["href"], link.get("titulo", "")),
            url_detalhe=link["href"],
            resumo=[parsers.limpar_texto(c) for c in link.get("linha", []) if c and c.lower() != "detalhar"],
        )
        page = await self._context.new_page()
        try:
            await self._navegar(page, link["href"])
            await self._aceitar_cookies(page)
            await self._maximizar_paginacao(page)
            await page.wait_for_function(sel.JS_DETALHE_CARREGADO, timeout=self._settings.search_timeout_ms)
            beneficio.dados = parsers.normalizar_campos(
                await page.evaluate(sel.JS_DADOS_ROTULADOS, sel.PANORAMA_DADOS))
            beneficio.tabelas = parsers.tabelas_para_registros(await page.evaluate(sel.JS_TABELAS, sel.AREA_PRINCIPAL))
        except (PlaywrightTimeout, BotError) as exc:
            # Falha num detalhe não derruba a consulta inteira
            logger.warning("Detalhe de %s incompleto: %s", beneficio.programa, exc)
            beneficio.observacao = "Detalhe não carregou no tempo limite; dados parciais."
        finally:
            await page.close()
        return beneficio

    # ------------------------------------------------------------ helpers
    async def _navegar(self, page: Page, url: str) -> None:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded",
                                   timeout=self._settings.navigation_timeout_ms)
        except PlaywrightTimeout as exc:
            raise TempoEsgotadoError(f"Timeout ao abrir {url}") from exc
        except PlaywrightError as exc:
            motivo = (exc.message or "").splitlines()[0].split(" at ")[0]  # sem call log interno
            raise PortalIndisponivelError(f"Portal indisponível: {motivo}") from exc
        if resp is not None and resp.status >= 400:
            raise PortalIndisponivelError(f"Portal respondeu HTTP {resp.status}")

    async def _verificar_bloqueio(self, page: Page) -> None:
        """Distingue o CAPTCHA do portal de um tempo esgotado comum."""
        try:
            bloqueado = await page.evaluate(sel.JS_VERIFICACAO_HUMANA)
        except PlaywrightError:
            return
        if bloqueado:
            raise BloqueioAntiBotError(
                "O Portal da Transparência exigiu verificação humana (CAPTCHA) e bloqueou a consulta automatizada")

    async def _aceitar_cookies(self, page: Page) -> None:
        try:
            await page.locator(sel.COOKIES_ACEITAR).click(timeout=2_500)
        except (PlaywrightTimeout, PlaywrightError):
            pass  # banner não exibido

    async def _expandir_secoes(self, page: Page) -> None:
        try:
            qtd = await page.evaluate(sel.JS_EXPANDIR_SECOES, sel.AREA_PRINCIPAL)
            if qtd:
                await page.wait_for_load_state("networkidle", timeout=10_000)
        except (PlaywrightTimeout, PlaywrightError):
            pass  # seguimos com o que estiver visível

    async def _maximizar_paginacao(self, page: Page) -> None:
        """Seleciona o maior tamanho de página nas tabelas de detalhe, se existir."""
        try:
            select = page.locator(sel.DETALHE_TAMANHO_PAGINA).first
            await select.wait_for(state="attached", timeout=5_000)
            opcoes = await select.locator("option").evaluate_all("os => os.map(o => o.value)")
            numericas = [o for o in opcoes if o.lstrip("-").isdigit()]
            if numericas:
                await select.select_option(max(numericas, key=int))
        except (PlaywrightTimeout, PlaywrightError):
            pass

    async def _texto(self, page: Page, seletor: str) -> str:
        try:
            return await page.locator(seletor).first.inner_text(timeout=2_000)
        except (PlaywrightTimeout, PlaywrightError):
            return ""

    async def _capturar_evidencia(self, page: Page) -> str:
        png = await page.screenshot(full_page=True, type="png")
        return base64.b64encode(png).decode("ascii")

    async def _evidencia_segura(self, page: Page) -> str | None:
        try:
            return await self._capturar_evidencia(page)
        except Exception:  # noqa: BLE001 - evidência é "best effort"
            return None
