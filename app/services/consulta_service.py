"""Orquestra a consulta: validação, execução do robô, mapeamento de erros e persistência."""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.bot.browser import BrowserManager
from app.bot.exceptions import BotError, NenhumResultadoError, PortalIndisponivelError, TempoEsgotadoError
from app.bot.portal_api import PortalApiClient
from app.bot.portal_scraper import PortalTransparenciaScraper
from app.core.config import Settings
from app.schemas import ConsultaRequest, ConsultaResponse, Parametros
from app.utils.validators import TipoTermo, classificar_termo, mascarar_documento, normalizar_termo

logger = logging.getLogger(__name__)

MSG_TEMPO_ESGOTADO = "Não foi possível retornar os dados no tempo de resposta solicitado"
MSG_ZERO_RESULTADOS = "Foram encontrados 0 resultados para o termo {termo}"
MSG_ERRO_INESPERADO = "Erro inesperado ao executar a consulta. Tente novamente."


def mensagem_de_erro(exc: Exception, tipo: TipoTermo, termo: str) -> tuple[str, str]:
    """Traduz exceções em (codigo, mensagem) conforme os cenários do desafio."""
    if isinstance(exc, NenhumResultadoError):
        if tipo == TipoTermo.NOME:
            return exc.codigo, MSG_ZERO_RESULTADOS.format(termo=termo)
        return exc.codigo, MSG_TEMPO_ESGOTADO  # CPF/NIS inexistente (cenário do desafio)
    if isinstance(exc, (TempoEsgotadoError, asyncio.TimeoutError)):
        return TempoEsgotadoError.codigo, MSG_TEMPO_ESGOTADO
    if isinstance(exc, PortalIndisponivelError):
        return exc.codigo, exc.mensagem
    return "ERRO_INTERNO", MSG_ERRO_INESPERADO


class ConsultaService:
    def __init__(self, browser: BrowserManager, settings: Settings,
                 scraper_cls: type[PortalTransparenciaScraper] = PortalTransparenciaScraper,
                 api: PortalApiClient | None = None):
        self._browser = browser
        self._settings = settings
        self._scraper_cls = scraper_cls
        self._api = api  # None = tudo pelo navegador

    async def executar(self, req: ConsultaRequest) -> ConsultaResponse:
        id_consulta = uuid.uuid4().hex[:16]
        agora = datetime.now(ZoneInfo(self._settings.timezone))
        inicio = time.perf_counter()
        tipo = classificar_termo(req.termo)
        termo = normalizar_termo(req.termo, tipo)
        filtro = req.filtro_beneficiario_programa_social
        # A API oficial só aceita documento; nome sempre vai pelo navegador
        fonte = "api_oficial" if self._api is not None and tipo != TipoTermo.NOME else "navegador"

        logger.info("[%s] Consulta %s '%s' filtro_social=%s fonte=%s", id_consulta, tipo.value,
                    mascarar_documento(termo), filtro, fonte)

        dados, evidencia, codigo, mensagem = None, None, None, None
        try:
            if fonte == "api_oficial":
                dados, evidencia = await asyncio.wait_for(
                    self._api.consultar(termo, tipo, filtro), timeout=self._settings.total_timeout_s)
            else:
                async with self._browser.contexto() as ctx:
                    scraper = self._scraper_cls(ctx, self._settings)
                    dados, evidencia = await asyncio.wait_for(
                        scraper.consultar(termo, filtro), timeout=self._settings.total_timeout_s)
        except Exception as exc:  # noqa: BLE001 - toda falha vira resposta JSON
            codigo, mensagem = mensagem_de_erro(exc, tipo, termo)
            if isinstance(exc, BotError):
                evidencia = exc.evidencia_base64
            log = logger.exception if codigo == "ERRO_INTERNO" else logger.warning
            log("[%s] Consulta falhou (%s): %s", id_consulta, codigo, exc)

        resposta = ConsultaResponse(
            id_consulta=id_consulta,
            status="erro" if codigo else "sucesso",
            codigo_erro=codigo,
            mensagem=mensagem,
            data_hora_consulta=agora,
            tempo_execucao_segundos=round(time.perf_counter() - inicio, 2),
            nome_arquivo=f"{id_consulta}_{agora:%Y%m%d_%H%M%S}.json",
            parametros=Parametros(termo=termo, tipo_termo=tipo, filtro_beneficiario_programa_social=filtro),
            fonte=fonte,
            dados=dados,
            evidencia_base64=evidencia,
        )
        logger.info("[%s] Finalizada: %s em %.2fs", id_consulta, resposta.status, resposta.tempo_execucao_segundos)
        self._salvar(resposta)
        return resposta

    def _salvar(self, resposta: ConsultaResponse) -> None:
        if not self._settings.save_output_files:
            return
        try:
            pasta = Path(self._settings.output_dir)
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / resposta.nome_arquivo).write_text(
                json.dumps(resposta.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            logger.exception("Não foi possível salvar o JSON localmente")
