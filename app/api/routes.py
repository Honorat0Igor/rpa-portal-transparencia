"""Endpoints REST."""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.schemas import ConsultaRequest, ConsultaResponse
from app.services.consulta_service import ConsultaService

router = APIRouter()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_service(request: Request) -> ConsultaService:
    return request.app.state.service


def verificar_api_key(chave: str | None = Security(api_key_header),
                      settings: Settings = Depends(get_settings)) -> None:
    if settings.api_key and not (chave and secrets.compare_digest(chave, settings.api_key)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key inválida ou ausente")


@router.get("/health", tags=["infra"])
async def health(request: Request) -> dict:
    browser = getattr(request.app.state, "browser", None)
    return {
        "status": "ok",
        "navegador_conectado": bool(browser and browser.conectado),
        "api_oficial_configurada": getattr(request.app.state, "api_oficial", None) is not None,
        "robos_em_execucao": browser.em_execucao if browser else 0,
    }


@router.post(
    "/api/v1/consultas",
    response_model=ConsultaResponse,
    tags=["consultas"],
    dependencies=[Depends(verificar_api_key)],
    summary="Consulta pessoa física no Portal da Transparência",
    description=(
        "Executa o robô e retorna os dados coletados + evidência em Base64. "
        "Erros de negócio (sem resultados, tempo esgotado) retornam HTTP 200 com "
        "`status=\"erro\"` e `mensagem`, para facilitar o consumo por ferramentas de workflow."
    ),
)
async def criar_consulta(payload: ConsultaRequest,
                         service: ConsultaService = Depends(get_service)) -> ConsultaResponse:
    return await service.executar(payload)
