"""Execução do robô sem API.

Exemplos:
    python -m app.cli "MARIA DA SILVA"
    python -m app.cli "SILVA" --filtro-social
    python -m app.cli 12345678909 --saida resultado.json
"""
import argparse
import asyncio
import json
from pathlib import Path

from app.bot.browser import BrowserManager
from app.bot.portal_api import PortalApiClient
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.schemas import ConsultaRequest
from app.services.consulta_service import ConsultaService


async def _rodar(args: argparse.Namespace) -> dict:
    settings = get_settings()
    if args.visivel:
        settings.headless = False
    configure_logging(settings.log_level)
    browser = BrowserManager(settings)
    await browser.start()
    api = await PortalApiClient.criar(browser.playwright, settings) if settings.portal_api_key else None
    try:
        service = ConsultaService(browser, settings, api=api)
        resposta = await service.executar(
            ConsultaRequest(termo=args.termo, filtro_beneficiario_programa_social=args.filtro_social))
        return resposta.model_dump(mode="json")
    finally:
        if api:
            await api.aclose()
        await browser.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Robô Portal da Transparência")
    parser.add_argument("termo", help="Nome, CPF ou NIS")
    parser.add_argument("--filtro-social", action="store_true", help="Filtro BENEFICIÁRIO DE PROGRAMA SOCIAL")
    parser.add_argument("--saida", help="Arquivo JSON de saída (opcional)")
    parser.add_argument("--visivel", action="store_true", help="Abre o navegador com interface (debug)")
    args = parser.parse_args()

    resultado = asyncio.run(_rodar(args))
    texto = json.dumps(resultado, ensure_ascii=False, indent=2)
    if args.saida:
        Path(args.saida).write_text(texto, encoding="utf-8")
        print(f"JSON salvo em {args.saida}")
    else:
        resumo = {k: v for k, v in resultado.items() if k != "evidencia_base64"}
        resumo["evidencia_base64"] = f"<{len(resultado.get('evidencia_base64') or '')} caracteres>"
        print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
