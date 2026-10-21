"""Funções puras de normalização (testáveis sem navegador)."""
import re
import unicodedata

PROGRAMAS_CONHECIDOS = {
    "auxilio-brasil": "Auxílio Brasil",
    "auxilio-emergencial": "Auxílio Emergencial",
    "novo-bolsa-familia": "Novo Bolsa Família",
    "bolsa-familia": "Bolsa Família",
    "bpc": "Benefício de Prestação Continuada (BPC)",
    "seguro-defeso": "Seguro Defeso",
    "garantia-safra": "Garantia-Safra",
    "peti": "PETI",
}


def limpar_texto(valor: str | None) -> str:
    return re.sub(r"\s+", " ", valor or "").strip()


def normalizar_rotulo(rotulo: str) -> str:
    """'Mês de Referência' -> 'mes_de_referencia'"""
    sem_acento = unicodedata.normalize("NFKD", rotulo or "").encode("ascii", "ignore").decode()
    chave = re.sub(r"[^a-zA-Z0-9]+", "_", sem_acento).strip("_").lower()
    return chave or "campo"


def normalizar_campos(bruto: dict[str, str]) -> dict[str, str]:
    return {normalizar_rotulo(k): limpar_texto(v) for k, v in (bruto or {}).items() if k}


def parse_total_resultados(texto: str | None) -> int | None:
    """'1.234' -> 1234 ; 'Foram encontrados 0 resultados' -> 0 ; '' -> None"""
    m = re.search(r"\d[\d.]*", texto or "")
    return int(m.group().replace(".", "")) if m else None


def tabelas_para_registros(tabelas: list[dict]) -> list[dict]:
    """Converte {titulo, headers, rows} em {titulo, registros:[{col: valor}]}."""
    resultado = []
    for tabela in tabelas or []:
        headers = [normalizar_rotulo(h) for h in tabela.get("headers") or []]
        registros = []
        for linha in tabela.get("rows") or []:
            chaves = headers if len(headers) == len(linha) else [f"coluna_{i + 1}" for i in range(len(linha))]
            registro = {k: limpar_texto(v) for k, v in zip(chaves, linha) if k and k != "detalhar"}
            if any(registro.values()):
                registros.append(registro)
        if registros:
            resultado.append({"titulo": limpar_texto(tabela.get("titulo")), "registros": registros})
    return resultado


def identificar_programa(href: str, titulo: str = "") -> str:
    alvo = f"{href} {normalizar_rotulo(titulo).replace('_', '-')}".lower()
    for slug, nome in PROGRAMAS_CONHECIDOS.items():
        if slug in alvo:
            return nome
    return limpar_texto(titulo) or "Benefício não identificado"
