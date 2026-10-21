"""Testa a camada HTTP com o serviço substituído (sem lifespan/navegador)."""
from datetime import datetime

from fastapi.testclient import TestClient

from app.api.routes import get_service
from app.core.config import Settings, get_settings
from app.main import app
from app.schemas import ConsultaResponse, Parametros
from app.utils.validators import TipoTermo


class FakeService:
    async def executar(self, req):
        return ConsultaResponse(
            id_consulta="abc", status="sucesso", data_hora_consulta=datetime(2026, 1, 1),
            tempo_execucao_segundos=1.0, nome_arquivo="abc_20260101_000000.json",
            parametros=Parametros(termo=req.termo, tipo_termo=TipoTermo.NOME,
                                  filtro_beneficiario_programa_social=False))


def cliente(api_key=None):
    app.dependency_overrides[get_service] = lambda: FakeService()
    app.dependency_overrides[get_settings] = lambda: Settings(api_key=api_key)
    return TestClient(app)  # sem "with": não dispara o lifespan (navegador)


def test_consulta_ok():
    r = cliente().post("/api/v1/consultas", json={"termo": "Maria"})
    assert r.status_code == 200
    assert r.json()["status"] == "sucesso"


def test_validacao_termo_curto():
    assert cliente().post("/api/v1/consultas", json={"termo": " a "}).status_code == 422


def test_api_key_obrigatoria_quando_configurada():
    c = cliente(api_key="segredo")
    assert c.post("/api/v1/consultas", json={"termo": "Maria"}).status_code == 401
    ok = c.post("/api/v1/consultas", json={"termo": "Maria"}, headers={"X-API-Key": "segredo"})
    assert ok.status_code == 200


def test_swagger_disponivel():
    assert cliente().get("/openapi.json").status_code == 200
