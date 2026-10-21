"""Exceções de domínio do robô. Cada uma mapeia para uma resposta de erro."""


class BotError(Exception):
    codigo = "ERRO_INTERNO"

    def __init__(self, mensagem: str = "", evidencia_base64: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.evidencia_base64 = evidencia_base64


class NenhumResultadoError(BotError):
    codigo = "NENHUM_RESULTADO"


class TempoEsgotadoError(BotError):
    codigo = "TEMPO_ESGOTADO"


class PortalIndisponivelError(BotError):
    codigo = "PORTAL_INDISPONIVEL"


class BloqueioAntiBotError(PortalIndisponivelError):
    """Portal exibiu verificação humana (CAPTCHA/WAF) em vez do conteúdo."""
    codigo = "BLOQUEIO_ANTIBOT"
