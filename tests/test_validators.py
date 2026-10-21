import pytest

from app.utils.validators import (TipoTermo, classificar_termo, cpf_valido, mascarar_documento,
                                  nis_valido, normalizar_termo)


@pytest.mark.parametrize("cpf,ok", [("529.982.247-25", True), ("52998224725", True),
                                    ("52998224724", False), ("11111111111", False), ("123", False)])
def test_cpf_valido(cpf, ok):
    assert cpf_valido(cpf) is ok


@pytest.mark.parametrize("nis,ok", [("120.12345.67-1", False), ("12056412545", True), ("00000000000", False)])
def test_nis_valido(nis, ok):
    assert nis_valido(nis) is ok


@pytest.mark.parametrize("termo,tipo", [
    ("529.982.247-25", TipoTermo.CPF),
    ("12056412545", TipoTermo.NIS),
    ("12345678901", TipoTermo.CPF),  # numérico inválido -> tratado como documento
    ("MARIA DA SILVA", TipoTermo.NOME),
    ("José 2", TipoTermo.NOME),
])
def test_classificar_termo(termo, tipo):
    assert classificar_termo(termo) == tipo


def test_normalizar_termo():
    assert normalizar_termo("529.982.247-25", TipoTermo.CPF) == "52998224725"
    assert normalizar_termo("  maria   da  silva ", TipoTermo.NOME) == "maria da silva"


def test_mascarar_documento():
    assert mascarar_documento("52998224725") == "***.982.247-**"
    assert mascarar_documento("MARIA") == "MARIA"
