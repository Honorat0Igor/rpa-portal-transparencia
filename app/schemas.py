"""Contratos de entrada/saída da API (geram o Swagger automaticamente)."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.utils.validators import TipoTermo


class ConsultaRequest(BaseModel):
    termo: str = Field(..., min_length=3, max_length=150,
                       description="Nome, CPF ou NIS", examples=["MARIA DA SILVA"])
    filtro_beneficiario_programa_social: bool = Field(
        False, description='Aplica o filtro "BENEFICIÁRIO DE PROGRAMA SOCIAL"')

    @field_validator("termo")
    @classmethod
    def termo_nao_vazio(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Informe ao menos 3 caracteres")
        return v


class Beneficio(BaseModel):
    programa: str
    url_detalhe: str
    resumo: list[str] = Field(default_factory=list, description="Linha da tabela no panorama")
    dados: dict[str, str] = Field(default_factory=dict)
    tabelas: list[dict[str, Any]] = Field(default_factory=list)
    observacao: str | None = None


class DadosPessoa(BaseModel):
    nome: str | None = None
    cpf: str | None = None
    localidade: str | None = None
    url_panorama: str
    dados_panorama: dict[str, str] = Field(default_factory=dict)
    recebimentos_recursos: list[dict[str, Any]] = Field(default_factory=list)
    beneficios: list[Beneficio] = Field(default_factory=list)


class Parametros(BaseModel):
    termo: str
    tipo_termo: TipoTermo
    filtro_beneficiario_programa_social: bool


class ConsultaResponse(BaseModel):
    id_consulta: str
    status: Literal["sucesso", "erro"]
    codigo_erro: str | None = None
    mensagem: str | None = None
    data_hora_consulta: datetime
    tempo_execucao_segundos: float
    nome_arquivo: str = Field(..., description="Sugestão de nome: [ID]_[DATA_HORA].json")
    parametros: Parametros
    fonte: Literal["api_oficial", "navegador"] | None = Field(
        None, description="Origem dos dados: API oficial (CPF/NIS) ou robô no navegador")
    dados: DadosPessoa | None = None
    evidencia_base64: str | None = Field(
        None, description="Screenshot PNG da tela de panorama em Base64 (apenas consultas via navegador)")
