"""Consulta de CPF/NIS pela API oficial do Portal da Transparência.

A API (https://api.portaldatransparencia.gov.br) não abre páginas nem passa
pelo CAPTCHA do site, mas só aceita CPF ou NIS — busca por nome continua no
scraper. Requer chave gratuita (header "chave-api-dados"), obtida em
https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email

As requisições usam o APIRequestContext do Playwright (mesma instância do
navegador), então todo o robô roda sobre o Playwright.

Fluxo:
 1. GET /pessoa-fisica -> dados cadastrais + indicadores de cada benefício
 2. Para cada benefício indicado, busca os pagamentos no endpoint do programa
"""
import asyncio
import json
import logging
import re
from typing import Any

from playwright.async_api import APIRequestContext, Playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from app.bot import parsers
from app.bot.exceptions import NenhumResultadoError, PortalIndisponivelError, TempoEsgotadoError
from app.core.config import Settings
from app.schemas import Beneficio, DadosPessoa
from app.utils.validators import TipoTermo

logger = logging.getLogger(__name__)

# (indicador em /pessoa-fisica, slug em parsers.PROGRAMAS_CONHECIDOS, endpoint, parâmetro do documento)
BENEFICIOS = [
    ("favorecidoNovoBolsaFamilia", "novo-bolsa-familia", "/novo-bolsa-familia-sacado-por-cpf-ou-nis", "codigo"),
    ("favorecidoBolsaFamilia", "bolsa-familia", "/bolsa-familia-sacado-por-cpf-ou-nis", "codigo"),
    ("favorecidoAuxilioBrasil", "auxilio-brasil", "/auxilio-brasil-sacado-por-cpf-ou-nis", "codigo"),
    ("auxilioEmergencial", "auxilio-emergencial", "/auxilio-emergencial-por-cpf-ou-nis", "codigoBeneficiario"),
    ("favorecidoBpc", "bpc", "/bpc-por-cpf-ou-nis", "codigo"),
    ("favorecidoSeguroDefeso", "seguro-defeso", "/seguro-defeso-codigo", "codigo"),
    ("favorecidoSafra", "garantia-safra", "/safra-codigo-por-cpf-ou-nis", "codigo"),
    ("favorecidoPeti", "peti", "/peti-por-cpf-ou-nis", "codigo"),
]
# Indicadores que caracterizam "beneficiário de programa social" (equivalente ao filtro do site)
INDICADORES_SOCIAIS = {b[0] for b in BENEFICIOS} | {"favorecidoAuxilioReconstrucao"}


def camel_para_snake(nome: str) -> str:
    """'nomeIBGE' -> 'nome_ibge' ; 'favorecidoBpc' -> 'favorecido_bpc'"""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", nome).lower()


def formatar_brl(valor: float) -> str:
    """1234.5 -> 'R$ 1.234,50'"""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def achatar(registro: dict, prefixo: str = "") -> dict[str, str]:
    """Achata objetos aninhados da API em {chave_snake: texto}, como as tabelas do scraper."""
    saida: dict[str, str] = {}
    for chave, valor in (registro or {}).items():
        nome = f"{prefixo}{camel_para_snake(chave)}"
        if chave == "id" or valor is None:
            continue
        if isinstance(valor, dict):
            saida.update(achatar(valor, f"{nome}_"))
        elif isinstance(valor, bool):
            saida[nome] = "Sim" if valor else "Não"
        elif isinstance(valor, (int, float)) and chave.lower().startswith("valor"):
            saida[nome] = formatar_brl(valor)
        else:
            saida[nome] = parsers.limpar_texto(str(valor))
    return saida


class PortalApiClient:
    def __init__(self, settings: Settings, requisicoes: APIRequestContext):
        self._settings = settings
        self._base = settings.portal_api_url.rstrip("/")
        self._req = requisicoes

    @classmethod
    async def criar(cls, playwright: Playwright, settings: Settings) -> "PortalApiClient":
        requisicoes = await playwright.request.new_context(
            extra_http_headers={"chave-api-dados": settings.portal_api_key or "", "Accept": "application/json"},
            timeout=settings.portal_api_timeout_s * 1000,
        )
        return cls(settings, requisicoes)

    async def aclose(self) -> None:
        try:
            await self._req.dispose()
        except Exception as exc:
            # No Windows, o Ctrl+C derruba o driver do Playwright antes do dispose; não há o que fechar.
            # O Playwright sinaliza isso com Exception genérica ("Connection closed while reading
            # from the driver"), não com PlaywrightError.
            logger.debug("APIRequestContext já encerrado: %s", exc)

    # ------------------------------------------------------------------ API
    async def consultar(self, termo: str, tipo: TipoTermo, filtro_social: bool) -> tuple[DadosPessoa, None]:
        """Mesmo contrato do scraper; não há screenshot, então a evidência é None."""
        parametro = "nis" if tipo == TipoTermo.NIS else "cpf"
        pessoa = await self._get("/pessoa-fisica", {parametro: termo})
        if not isinstance(pessoa, dict) or not pessoa.get("nome"):
            raise NenhumResultadoError(f"Documento sem registro na API ({parametro})")
        if filtro_social and not any(pessoa.get(k) for k in INDICADORES_SOCIAIS):
            raise NenhumResultadoError("Pessoa não é beneficiária de programa social")

        indicados = [b for b in BENEFICIOS if pessoa.get(b[0])]
        beneficios = list(await asyncio.gather(*(self._coletar_beneficio(termo, *b) for b in indicados)))
        logger.info("API oficial: %d benefício(s) detalhado(s)", len(beneficios))

        return DadosPessoa(
            nome=pessoa.get("nome"),
            cpf=pessoa.get("cpf"),
            url_panorama=f"{self._base}/pessoa-fisica",
            dados_panorama=achatar(pessoa),
            recebimentos_recursos=[
                {"titulo": b.programa, "registros": [{"registros": b.resumo[0], "valor_total": b.resumo[1]}]}
                for b in beneficios if len(b.resumo) == 2
            ],
            beneficios=beneficios,
        ), None

    # --------------------------------------------------------------- etapas
    async def _coletar_beneficio(self, documento: str, _indicador: str, slug: str,
                                 endpoint: str, parametro: str) -> Beneficio:
        beneficio = Beneficio(programa=parsers.PROGRAMAS_CONHECIDOS[slug], url_detalhe=f"{self._base}{endpoint}")
        registros: list[dict] = []
        try:
            for pagina in range(1, self._settings.portal_api_max_paginas + 1):
                lote = await self._get(endpoint, {parametro: documento, "pagina": pagina})
                if not lote:
                    break
                registros.extend(lote)
            else:
                beneficio.observacao = (f"Exibindo as {self._settings.portal_api_max_paginas} primeiras páginas; "
                                        "pode haver mais registros.")
        except (TempoEsgotadoError, PortalIndisponivelError, NenhumResultadoError) as exc:
            # Falha num benefício não derruba a consulta inteira
            logger.warning("Detalhe de %s incompleto: %s", beneficio.programa, exc)
            beneficio.observacao = "Detalhe não carregou pela API; dados parciais."

        linhas = [achatar(r) for r in registros]
        total = sum(v for r in registros for k, v in r.items()
                    if k.lower().startswith("valor") and isinstance(v, (int, float)))
        beneficio.resumo = [f"{len(registros)} registro(s)", formatar_brl(total)]
        beneficio.tabelas = [{"titulo": beneficio.programa, "registros": linhas}] if linhas else []
        return beneficio

    # ------------------------------------------------------------ helpers
    async def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        try:
            r = await self._req.get(f"{self._base}{endpoint}", params={k: str(v) for k, v in params.items()})
            corpo = await r.body()
        except PlaywrightError as exc:
            motivo = (exc.message or type(exc).__name__).splitlines()[0]
            # O APIRequestContext sinaliza timeout com Error genérico ("Request timed out after ...")
            if isinstance(exc, PlaywrightTimeout) or "timed out" in motivo.lower():
                raise TempoEsgotadoError(f"API oficial não respondeu a tempo ({endpoint})") from exc
            raise PortalIndisponivelError(f"API oficial indisponível: {motivo}") from exc

        if r.status in (401, 403):
            raise PortalIndisponivelError("Chave da API oficial (PORTAL_API_KEY) inválida ou não autorizada")
        if r.status == 429:
            raise PortalIndisponivelError("Limite de requisições da API oficial atingido; tente em instantes")
        if r.status in (400, 404):
            raise NenhumResultadoError(f"API oficial respondeu HTTP {r.status} em {endpoint}")
        if not r.ok:
            raise PortalIndisponivelError(f"API oficial respondeu HTTP {r.status}")
        if not corpo:
            return None
        try:
            return json.loads(corpo)
        except ValueError as exc:
            raise PortalIndisponivelError("API oficial devolveu resposta inválida (não-JSON)") from exc
