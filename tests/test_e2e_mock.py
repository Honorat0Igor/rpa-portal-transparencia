"""E2E: roda o robô REAL (Playwright + Chromium) contra um portal simulado local.

Valida fluxo, scripts JS de extração, concorrência e cenários de erro sem
depender do portal oficial. Pulado se o Chromium não estiver disponível.
Para usar um binário específico: CHROMIUM_EXECUTABLE_PATH=/caminho/chrome
"""
import asyncio
import base64
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.bot.browser import BrowserManager
from app.core.config import Settings
from app.schemas import ConsultaRequest
from app.services.consulta_service import ConsultaService

MOCK_DIR = Path(__file__).parent / "fixtures" / "portal_mock"


class HtmlHandler(SimpleHTTPRequestHandler):
    def guess_type(self, path):
        return "text/html; charset=utf-8"

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def portal_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(HtmlHandler, directory=str(MOCK_DIR)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


async def _rodar(portal_url, consultas):
    settings = Settings(portal_base_url=portal_url, save_output_files=False, search_timeout_ms=3_000,
                        max_concurrent_bots=3, bot_start_interval_s=0,
                        chromium_executable_path=os.getenv("CHROMIUM_EXECUTABLE_PATH"))
    browser = BrowserManager(settings)
    try:
        await browser.start()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium indisponível: {exc}")
    try:
        service = ConsultaService(browser, settings)
        return await asyncio.gather(*(service.executar(ConsultaRequest(
            termo=t, filtro_beneficiario_programa_social=f)) for t, f in consultas))
    finally:
        await browser.stop()


def test_cenarios_do_desafio_em_paralelo(portal_url):
    sucesso, filtrado, nome_vazio, cpf_vazio = asyncio.run(_rodar(portal_url, [
        ("Maria da Silva", False),
        ("Silva", True),
        ("Nome XYZ", False),
        ("00000000000", False),
    ]))

    assert sucesso.status == "sucesso", sucesso.mensagem
    assert sucesso.dados.nome == "MARIA DA SILVA"
    assert sucesso.dados.localidade == "RIO DE JANEIRO - RJ"
    assert base64.b64decode(sucesso.evidencia_base64)[:4] == b"\x89PNG"
    programas = {b.programa: b for b in sucesso.dados.beneficios}
    assert set(programas) == {"Auxílio Brasil", "Bolsa Família"}
    registros_ab = programas["Auxílio Brasil"].tabelas[0]["registros"]
    assert registros_ab[0] == {"mes_de_referencia": "01/2022", "uf": "RJ",
                               "municipio": "RIO DE JANEIRO", "valor": "R$ 400,00"}

    assert filtrado.status == "sucesso"
    assert "f=social" in filtrado.dados.url_panorama

    assert nome_vazio.mensagem == "Foram encontrados 0 resultados para o termo Nome XYZ"
    assert cpf_vazio.mensagem == "Não foi possível retornar os dados no tempo de resposta solicitado"
