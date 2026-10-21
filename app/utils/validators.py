"""Validação e classificação do termo de busca (CPF, NIS ou Nome)."""
import re
from enum import Enum


class TipoTermo(str, Enum):
    CPF = "CPF"
    NIS = "NIS"
    NOME = "NOME"


def apenas_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def cpf_valido(cpf: str) -> bool:
    cpf = apenas_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for posicao in (9, 10):
        soma = sum(int(cpf[i]) * (posicao + 1 - i) for i in range(posicao))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[posicao]):
            return False
    return True


def nis_valido(nis: str) -> bool:
    """Valida NIS/PIS/PASEP (pesos 3,2,9,8,7,6,5,4,3,2)."""
    nis = apenas_digitos(nis)
    if len(nis) != 11 or nis == nis[0] * 11:
        return False
    pesos = (3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    resto = sum(int(d) * p for d, p in zip(nis[:10], pesos)) % 11
    digito = 0 if resto < 2 else 11 - resto
    return digito == int(nis[10])


def classificar_termo(termo: str) -> TipoTermo:
    """Termos numéricos são tratados como documento; o resto como nome.

    Um número de 11 dígitos pode ser CPF ou NIS. Se for CPF válido -> CPF,
    se for NIS válido -> NIS; caso contrário assumimos CPF (o portal decide).
    """
    texto = (termo or "").strip()
    digitos = apenas_digitos(texto)
    sem_pontuacao = re.sub(r"[\s.\-/]", "", texto)
    if digitos and sem_pontuacao.isdigit():
        if cpf_valido(digitos):
            return TipoTermo.CPF
        if nis_valido(digitos):
            return TipoTermo.NIS
        return TipoTermo.CPF
    return TipoTermo.NOME


def normalizar_termo(termo: str, tipo: TipoTermo) -> str:
    if tipo in (TipoTermo.CPF, TipoTermo.NIS):
        return apenas_digitos(termo)
    return re.sub(r"\s+", " ", termo).strip()


def mascarar_documento(valor: str) -> str:
    """Mascara documentos em logs (LGPD): 12345678901 -> ***.456.789-**"""
    d = apenas_digitos(valor)
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    return valor
