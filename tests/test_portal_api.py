"""Testa o cliente da API oficial com o APIRequestContext REAL do Playwright
contra uma API simulada local (sem rede externa e sem abrir navegador)."""
import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.async_api import async_playwright

from app.bot.exceptions import NenhumResultadoError, PortalIndisponivelError, TempoEsgotadoError
from app.bot.portal_api import PortalApiClient, achatar, camel_para_snake, formatar_brl
from app.core.config import Settings
from app.utils.validators import TipoTermo

PESSOA = {"cpf": "***.982.247-**", "nome": "MARIA DA SILVA", "nis": "",
          "favorecidoAuxilioBrasil": True, "favorecidoBpc": False, "servidor": False}
PAGAMENTO = {"id": 1, "dataMesReferencia": "2022-01-01", "valorSaque": 400.0,
             "municipio": {"nomeIBGE": "RIO DE JANEIRO", "uf": {"sigla": "RJ"}}}


class ApiSimulada(BaseHTTPRequestHandler):
    """Delega cada GET para `self.server.rota(path, params)` -> (status, corpo)."""

    def do_GET(self):
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.server.chamadas.append({"path": url.path, "params": params,
                                     "chave": self.headers.get("chave-api-dados")})
        status, corpo = self.server.rota(url.path, params)
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def servidor():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApiSimulada)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


def portal(pessoa=PESSOA, pagamentos=(PAGAMENTO,)):
    def rota(path, params):
        if path.endswith("/pessoa-fisica"):
            return 200, pessoa
        return 200, list(pagamentos) if params["pagina"] == "1" else []
    return rota


def consultar(servidor, rota, termo="52998224725", tipo=TipoTermo.CPF, filtro=False, url=None, **cfg):
    servidor.rota, servidor.chamadas = rota, []
    base = url or f"http://127.0.0.1:{servidor.server_address[1]}/api-de-dados"
    settings = Settings(portal_api_url=base, portal_api_key="chave", save_output_files=False, **cfg)

    async def rodar():
        async with async_playwright() as pw:
            api = await PortalApiClient.criar(pw, settings)
            try:
                return await api.consultar(termo, tipo, filtro)
            finally:
                await api.aclose()

    return asyncio.run(rodar())


def test_sucesso_cpf_com_beneficio(servidor):
    dados, evidencia = consultar(servidor, portal())
    assert evidencia is None
    assert dados.nome == "MARIA DA SILVA"
    pessoa = servidor.chamadas[0]
    assert pessoa == {"path": "/api-de-dados/pessoa-fisica", "params": {"cpf": "52998224725"}, "chave": "chave"}
    [beneficio] = dados.beneficios  # só o benefício indicado como True é consultado
    assert beneficio.programa == "Auxílio Brasil"
    assert beneficio.resumo == ["1 registro(s)", "R$ 400,00"]
    registro = beneficio.tabelas[0]["registros"][0]
    assert registro["municipio_nome_ibge"] == "RIO DE JANEIRO"
    assert registro["municipio_uf_sigla"] == "RJ"
    assert registro["valor_saque"] == "R$ 400,00"
    assert "id" not in registro


def test_nis_usa_parametro_nis(servidor):
    consultar(servidor, portal(), termo="12345678919", tipo=TipoTermo.NIS)
    assert servidor.chamadas[0]["params"] == {"nis": "12345678919"}


@pytest.mark.parametrize("resposta", [
    (200, {"cpf": None, "nome": None}),
    (200, b""),
    (404, b""),
    (400, {"erro": "CPF inválido"}),
])
def test_documento_inexistente(servidor, resposta):
    with pytest.raises(NenhumResultadoError):
        consultar(servidor, lambda path, params: resposta)


def test_filtro_social_sem_beneficio(servidor):
    pessoa = {**PESSOA, "favorecidoAuxilioBrasil": False}
    with pytest.raises(NenhumResultadoError):
        consultar(servidor, portal(pessoa=pessoa), filtro=True)


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_erros_http(servidor, status):
    with pytest.raises(PortalIndisponivelError):
        consultar(servidor, lambda path, params: (status, {"Erro na API": "x"}))


def test_timeout(servidor):
    def lenta(path, params):
        time.sleep(1.5)
        return 200, PESSOA

    with pytest.raises(TempoEsgotadoError):
        consultar(servidor, lenta, portal_api_timeout_s=0.3)


def test_api_fora_do_ar(servidor):
    with pytest.raises(PortalIndisponivelError):
        consultar(servidor, portal(), url="http://127.0.0.1:9/api-de-dados")


def test_falha_em_beneficio_nao_derruba_consulta(servidor):
    def rota(path, params):
        return (200, PESSOA) if path.endswith("/pessoa-fisica") else (503, b"")

    dados, _ = consultar(servidor, rota)
    assert dados.beneficios[0].observacao.startswith("Detalhe não carregou")


def test_limite_de_paginas(servidor):
    def rota(path, params):  # sempre há mais páginas
        return (200, PESSOA) if path.endswith("/pessoa-fisica") else (200, [PAGAMENTO])

    dados, _ = consultar(servidor, rota, portal_api_max_paginas=2)
    assert len(servidor.chamadas) == 3  # pessoa + 2 páginas
    assert dados.beneficios[0].resumo == ["2 registro(s)", "R$ 800,00"]
    assert "primeiras páginas" in dados.beneficios[0].observacao


def test_helpers():
    assert camel_para_snake("nomeIBGE") == "nome_ibge"
    assert formatar_brl(1234.5) == "R$ 1.234,50"
    assert achatar({"a": True, "b": None, "c": {"dX": 1}}) == {"a": "Sim", "c_d_x": "1"}
