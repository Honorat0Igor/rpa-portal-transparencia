from app.bot import parsers


def test_normalizar_rotulo():
    assert parsers.normalizar_rotulo("Mês de Referência") == "mes_de_referencia"
    assert parsers.normalizar_rotulo("CPF") == "cpf"
    assert parsers.normalizar_rotulo("  ") == "campo"


def test_parse_total_resultados():
    assert parsers.parse_total_resultados("1.234") == 1234
    assert parsers.parse_total_resultados("Foram encontrados 0 resultados") == 0
    assert parsers.parse_total_resultados("") is None


def test_tabelas_para_registros_com_cabecalho():
    tabelas = [{"titulo": "Auxílio Brasil", "headers": ["Mês", "Valor", "Detalhar"],
                "rows": [["01/2023", "R$ 600,00", "Detalhar"], ["", "", ""]]}]
    r = parsers.tabelas_para_registros(tabelas)
    assert r == [{"titulo": "Auxílio Brasil", "registros": [{"mes": "01/2023", "valor": "R$ 600,00"}]}]


def test_tabelas_sem_cabecalho_usa_colunas_genericas():
    r = parsers.tabelas_para_registros([{"titulo": "", "headers": [], "rows": [["a", "b"]]}])
    assert r[0]["registros"] == [{"coluna_1": "a", "coluna_2": "b"}]


def test_identificar_programa():
    assert parsers.identificar_programa("https://x/beneficios/auxilio-brasil/123") == "Auxílio Brasil"
    assert parsers.identificar_programa("https://x/beneficios/novo-bolsa-familia/1") == "Novo Bolsa Família"
    assert parsers.identificar_programa("https://x/beneficios/consulta?id=1", "Bolsa Família") == "Bolsa Família"
    assert parsers.identificar_programa("https://x/outro", "Outro Programa") == "Outro Programa"
