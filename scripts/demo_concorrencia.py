"""Demonstra execuções SIMULTÂNEAS do robô via API (útil na apresentação).

Uso:
    python scripts/demo_concorrencia.py --url http://localhost:8000 \
        "MARIA DA SILVA" "SILVA:social" "00000000000" "NOME QUE NAO EXISTE XYZ"

Sufixo ":social" ativa o filtro de beneficiário de programa social.
Se a variável de ambiente API_KEY estiver definida, é enviada no header X-API-Key.
"""
import argparse
import asyncio
import os
import sys
import time

import httpx

SUFIXO_SOCIAL = ":social"


def agora() -> str:
    return time.strftime("%H:%M:%S")


async def consultar(client: httpx.AsyncClient, url: str, termo_bruto: str) -> bool:
    """Executa uma consulta e imprime o resultado. Retorna True em caso de sucesso.

    Nunca propaga exceções, para que a falha de uma consulta não interrompa as demais.
    """
    filtro = termo_bruto.endswith(SUFIXO_SOCIAL)
    termo = termo_bruto.removesuffix(SUFIXO_SOCIAL).strip()
    inicio = time.perf_counter()
    print(f"[{agora()}] -> iniciando '{termo}' (filtro={filtro})", flush=True)

    def fim(msg: str) -> None:
        print(f"[{agora()}] <- '{termo}': {msg} | {time.perf_counter() - inicio:.1f}s", flush=True)

    try:
        r = await client.post(f"{url}/api/v1/consultas",
                              json={"termo": termo, "filtro_beneficiario_programa_social": filtro})
    except httpx.TimeoutException:
        fim("ERRO: tempo limite excedido")
        return False
    except httpx.HTTPError as e:
        fim(f"ERRO de conexão: {type(e).__name__}: {e}")
        return False

    try:
        dados = r.json()
    except ValueError:
        dados = None

    if r.is_error:
        detalhe = dados.get("detail") if isinstance(dados, dict) else r.text[:200]
        fim(f"HTTP {r.status_code}: {detalhe}")
        return False
    if not isinstance(dados, dict):
        fim(f"ERRO: resposta inesperada (HTTP {r.status_code}): {r.text[:200]}")
        return False

    resumo = dados.get("mensagem") or (dados.get("dados") or {}).get("nome")
    fim(f"{dados.get('status')} | {resumo}")
    # A API responde HTTP 200 mesmo quando o robô falha; o resultado real está em "status".
    return dados.get("status") != "erro"


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://localhost:8000", help="URL base da API")
    p.add_argument("--timeout", type=float, default=300, help="timeout por consulta, em segundos")
    p.add_argument("termos", nargs="+", help=f"termos de busca (sufixo '{SUFIXO_SOCIAL}' ativa o filtro)")
    a = p.parse_args()

    if any(not t.removesuffix(SUFIXO_SOCIAL).strip() for t in a.termos):
        p.error("termos não podem ser vazios")

    url = a.url.rstrip("/")
    api_key = os.getenv("API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}
    # Garante que nenhuma consulta fique esperando na fila do pool de conexões.
    limites = httpx.Limits(max_connections=len(a.termos))

    inicio = time.perf_counter()
    async with httpx.AsyncClient(timeout=a.timeout, headers=headers, limits=limites) as client:
        resultados = await asyncio.gather(*(consultar(client, url, t) for t in a.termos))

    ok = sum(resultados)
    print(f"\nTotal: {time.perf_counter() - inicio:.1f}s para {len(a.termos)} consultas simultâneas "
          f"({ok} ok, {len(a.termos) - ok} com erro)")
    return 0 if ok == len(a.termos) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
