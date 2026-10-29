"""Testa o mapeamento de cenários do desafio sem abrir navegador (scraper fake)."""
import asyncio
from contextlib import asynccontextmanager

import pytest

from app.bot.exceptions import BloqueioAntiBotError, NenhumResultadoError, TempoEsgotadoError
from app.core.config import Settings
from app.schemas import ConsultaRequest, DadosPessoa
from app.services.consulta_service import ConsultaService


class FakeBrowser:
    @asynccontextmanager
    async def contexto(self):
        yield object()


class FakeApi:
    def __init__(self):
        self.chamadas = []

    async def consultar(self, termo, tipo, filtro):
        self.chamadas.append(termo)
        return DadosPessoa(nome="VIA API", url_panorama="http://api"), None


def criar_service(comportamento, api=None, **cfg):
    class FakeScraper:
        def __init__(self, ctx, settings):
            pass

        async def consultar(self, termo, filtro):
            return await comportamento(termo, filtro)

    settings = Settings(save_output_files=False, **cfg)
    return ConsultaService(FakeBrowser(), settings, scraper_cls=FakeScraper, api=api)


def executar(service, termo, filtro=False):
    return asyncio.run(service.executar(ConsultaRequest(termo=termo, filtro_beneficiario_programa_social=filtro)))


def test_sucesso_nome():
    async def ok(termo, filtro):
        return DadosPessoa(nome="MARIA", url_panorama="http://x"), "QkFTRTY0"

    r = executar(criar_service(ok), "Maria da Silva", True)
    assert r.status == "sucesso"
    assert r.dados.nome == "MARIA"
    assert r.evidencia_base64 == "QkFTRTY0"
    assert r.parametros.filtro_beneficiario_programa_social is True
    assert r.nome_arquivo.startswith(r.id_consulta) and r.nome_arquivo.endswith(".json")


def test_nome_inexistente():
    async def vazio(termo, filtro):
        raise NenhumResultadoError("0")

    r = executar(criar_service(vazio), "Nome Inexistente XYZ")
    assert r.status == "erro"
    assert r.mensagem == "Foram encontrados 0 resultados para o termo Nome Inexistente XYZ"


@pytest.mark.parametrize("exc", [NenhumResultadoError("0"), TempoEsgotadoError("t")])
def test_cpf_inexistente_ou_timeout(exc):
    async def falha(termo, filtro):
        raise exc

    r = executar(criar_service(falha), "529.982.247-25")
    assert r.status == "erro"
    assert r.mensagem == "Não foi possível retornar os dados no tempo de resposta solicitado"


def test_timeout_total():
    async def lento(termo, filtro):
        await asyncio.sleep(5)

    r = executar(criar_service(lento, total_timeout_s=0.1), "Maria")
    assert r.codigo_erro == "TEMPO_ESGOTADO"


async def _scraper_ok(termo, filtro):
    return DadosPessoa(nome="VIA NAVEGADOR", url_panorama="http://x"), "QkFTRTY0"


def test_documento_usa_api_oficial_quando_configurada():
    api = FakeApi()
    r = executar(criar_service(_scraper_ok, api=api), "529.982.247-25")
    assert r.fonte == "api_oficial"
    assert r.dados.nome == "VIA API"
    assert r.evidencia_base64 is None
    assert api.chamadas == ["52998224725"]


def test_nome_continua_no_navegador_mesmo_com_api():
    api = FakeApi()
    r = executar(criar_service(_scraper_ok, api=api), "Maria da Silva")
    assert r.fonte == "navegador"
    assert r.dados.nome == "VIA NAVEGADOR"
    assert api.chamadas == []


def test_documento_sem_api_usa_navegador():
    r = executar(criar_service(_scraper_ok), "529.982.247-25")
    assert r.fonte == "navegador"


def _bloqueia_vezes(n):
    tentativas = []

    async def comportamento(termo, filtro):
        tentativas.append(termo)
        if len(tentativas) <= n:
            raise BloqueioAntiBotError("captcha", evidencia_base64="Q0FQVENIQQ==")
        return DadosPessoa(nome="MARIA", url_panorama="http://x"), "QkFTRTY0"

    return comportamento, tentativas


def test_captcha_tenta_de_novo_e_recupera():
    comportamento, tentativas = _bloqueia_vezes(2)
    r = executar(criar_service(comportamento, antibot_retry_wait_s=0), "Maria da Silva")
    assert r.status == "sucesso"
    assert len(tentativas) == 3


def test_captcha_persistente_desiste_apos_limite():
    comportamento, tentativas = _bloqueia_vezes(99)
    r = executar(criar_service(comportamento, antibot_retry_wait_s=0, antibot_max_retries=2), "Maria da Silva")
    assert r.codigo_erro == "BLOQUEIO_ANTIBOT"
    assert r.evidencia_base64 == "Q0FQVENIQQ=="
    assert len(tentativas) == 3


def test_captcha_nao_espera_alem_do_timeout_total():
    comportamento, tentativas = _bloqueia_vezes(99)
    r = executar(criar_service(comportamento, antibot_retry_wait_s=60, total_timeout_s=30), "Maria da Silva")
    assert r.codigo_erro == "BLOQUEIO_ANTIBOT"  # desiste na hora em vez de virar TEMPO_ESGOTADO
    assert len(tentativas) == 1


def test_captcha_nao_tenta_de_novo_se_a_tentativa_nao_cabe():
    tentativas = []

    async def lento_e_bloqueado(termo, filtro):
        tentativas.append(termo)
        await asyncio.sleep(0.3)  # cada tentativa leva 0.3s até o CAPTCHA
        raise BloqueioAntiBotError("captcha")

    # Restam ~0.2s após a 1ª tentativa: cabe a espera (0.05s), mas não outra tentativa de 0.3s
    service = criar_service(lento_e_bloqueado, antibot_retry_wait_s=0.05, total_timeout_s=0.5)
    r = executar(service, "Maria da Silva")
    assert r.codigo_erro == "BLOQUEIO_ANTIBOT"
    assert len(tentativas) == 1


def test_erro_inesperado_nao_vaza_detalhes():
    async def quebra(termo, filtro):
        raise RuntimeError("segredo interno")

    r = executar(criar_service(quebra), "Maria")
    assert r.codigo_erro == "ERRO_INTERNO"
    assert "segredo" not in r.mensagem
