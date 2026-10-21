# Robô Portal da Transparência — RPA e Hiperautomação

Robô em Python + Playwright que consulta **Pessoa Física** no
[Portal da Transparência](https://portaldatransparencia.gov.br), coleta o
*Panorama da relação da pessoa com o Governo Federal*, detalha os benefícios
(Auxílio Brasil, Auxílio Emergencial, Bolsa Família, etc.), captura evidência
em Base64 e devolve tudo em JSON — exposto como **API REST com Swagger**.

> Solução para o [desafio técnico público de RPA da mostQI](https://github.com/mostqi/desafios-fullstack-python/blob/main/desafio-01/README.md), feita como projeto de estudo.
>
> **Status:** Parte 1 (robô + API) ✅ concluída · Parte 2 (workflow com Google Drive/Sheets) 🚧 em andamento

## Funcionalidades

- Busca por **Nome, CPF ou NIS** (detecção automática com validação de dígitos)
- **Fonte híbrida**: CPF/NIS pela [API oficial](https://api.portaldatransparencia.gov.br)
  (sem navegador nem CAPTCHA) quando `PORTAL_API_KEY` está definida; nomes sempre
  pelo robô no navegador, já que a API oficial não busca por nome
- Filtro opcional **"BENEFICIÁRIO DE PROGRAMA SOCIAL"**
- Coleta do panorama + detalhamento de cada benefício
- Screenshot da tela de panorama em **Base64 (PNG)**
- **Headless** e **execuções simultâneas** (contextos isolados + semáforo)
- API REST documentada (`/docs`), autenticação por `X-API-Key`
- JSON salvo localmente como `[ID]_[DATA_HORA].json`
- Testes unitários, de API e **E2E com navegador real contra portal simulado**

## Arquitetura

```
app/
├── main.py                  # FastAPI + ciclo de vida do navegador
├── api/routes.py            # Endpoints, autenticação por API key
├── schemas.py               # Contratos Pydantic (geram o Swagger)
├── services/consulta_service.py  # Orquestração, timeout global, mapeamento de erros
├── bot/
│   ├── browser.py           # 1 Chromium compartilhado, 1 contexto por consulta, semáforo
│   ├── portal_scraper.py    # Fluxo do robô (busca → panorama → evidência → benefícios)
│   ├── portal_api.py        # CPF/NIS pela API oficial via APIRequestContext do Playwright
│   ├── selectors.py         # ÚNICO ponto que conhece o HTML do portal
│   ├── parsers.py           # Funções puras de normalização (100% testáveis)
│   └── exceptions.py        # Erros de domínio
├── utils/validators.py      # CPF/NIS, classificação do termo, máscara LGPD
└── cli.py                   # Execução via linha de comando
scripts/demo_concorrencia.py # Dispara N consultas simultâneas (demonstração)
tests/                       # Unitários, API e E2E (portal simulado em tests/fixtures)
docs/PARTE2_ACTIVEPIECES.md  # Workflow de hiperautomação (Drive + Sheets)
```

## Decisões técnicas

Resumo das principais escolhas — detalhes, desafios enfrentados e melhorias futuras no [Relatório](RELATORIO.md).

- **Playwright (async) em vez de Selenium:** espera automática por elementos e API assíncrona nativa, essencial para execuções simultâneas num único processo.
- **Um navegador, vários contextos:** um único Chromium compartilhado e um `BrowserContext` isolado por consulta, com semáforo limitando o paralelismo.
- **Busca pela URL da consulta:** os parâmetros vão direto na URL, eliminando cliques e digitação frágeis no formulário.

## Como executar

### Local

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
playwright install --with-deps chromium
cp .env.example .env

# API (Swagger em http://localhost:8000/docs)
uvicorn app.main:app --reload

# ou CLI
python -m app.cli "MARIA DA SILVA"
python -m app.cli "SILVA" --filtro-social --saida resultado.json
python -m app.cli 52998224725 --visivel          # abre o navegador (debug)
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

> Rode com **um único worker** do Uvicorn. A concorrência é feita por asyncio
> dentro do processo; múltiplos workers criariam vários Chromium e estourariam memória.

## API

`POST /api/v1/consultas` (header `X-API-Key` se `API_KEY` estiver definida)

```json
{ "termo": "MARIA DA SILVA", "filtro_beneficiario_programa_social": true }
```

Resposta (resumida):

```json
{
  "id_consulta": "9f1c2a7b3d4e5f60",
  "status": "sucesso",
  "codigo_erro": null,
  "mensagem": null,
  "data_hora_consulta": "2026-10-16T14:32:10-03:00",
  "tempo_execucao_segundos": 18.4,
  "nome_arquivo": "9f1c2a7b3d4e5f60_20261016_143210.json",
  "parametros": { "termo": "MARIA DA SILVA", "tipo_termo": "NOME", "filtro_beneficiario_programa_social": true },
  "dados": {
    "nome": "MARIA DA SILVA", "cpf": "***.982.247-**", "localidade": "RIO DE JANEIRO - RJ",
    "url_panorama": "https://portaldatransparencia.gov.br/busca/pessoa-fisica/...",
    "dados_panorama": { "...": "..." },
    "recebimentos_recursos": [ { "titulo": "Auxílio Brasil", "registros": [ { "nis": "...", "valor_recebido": "R$ 4.800,00" } ] } ],
    "beneficios": [
      { "programa": "Auxílio Brasil", "url_detalhe": "...", "resumo": ["..."],
        "tabelas": [ { "titulo": "", "registros": [ { "mes_de_referencia": "01/2022", "uf": "RJ", "municipio": "RIO DE JANEIRO", "valor": "R$ 400,00" } ] } ] }
    ]
  },
  "evidencia_base64": "iVBORw0KGgo..."
}
```

O campo `fonte` indica a origem dos dados (`api_oficial` ou `navegador`). Consultas
pela API oficial não têm screenshot, então `evidencia_base64` vem `null`.

`GET /health` — status do navegador, se a API oficial está configurada e quantidade de robôs em execução.

### API oficial do Portal da Transparência

1. Cadastre seu e-mail em <https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email>
   e receba a chave (gratuita).
2. Defina `PORTAL_API_KEY=<sua chave>` no `.env` e reinicie a API.

A API oficial tem limite de requisições por minuto; cada consulta faz 1 chamada
para a pessoa + até `PORTAL_API_MAX_PAGINAS` chamadas por benefício recebido.
Se o site exibir verificação humana (CAPTCHA) para o robô, a consulta retorna
`codigo_erro: "BLOQUEIO_ANTIBOT"`.

### Cenários de teste

| Cenário | Entrada | Saída |
|---|---|---|
| Sucesso (CPF/NIS) | CPF ou NIS válido | `status: sucesso` + dados + evidência |
| Erro (CPF/NIS) | Documento inexistente | `Não foi possível retornar os dados no tempo de resposta solicitado` |
| Sucesso (Nome) | Nome completo | Primeiro registro encontrado + evidência |
| Erro (Nome) | Nome inexistente | `Foram encontrados 0 resultados para o termo …` |
| Filtrado | Sobrenome + filtro social | Primeiro registro filtrado + evidência |

Erros de negócio retornam **HTTP 200** com `status: "erro"` (decisão consciente:
ferramentas de workflow interrompem o fluxo em respostas não-2xx). Erros de
validação retornam 422 e autenticação 401.

## Execução simultânea

```bash
python scripts/demo_concorrencia.py "MARIA DA SILVA" "SILVA:social" "00000000000" "NOME XYZ INEXISTENTE"
```

`MAX_CONCURRENT_BOTS` controla quantos robôs rodam ao mesmo tempo; as demais
requisições aguardam na fila do semáforo.

## Testes

```bash
pytest
```

- `test_validators.py` / `test_parsers.py`: funções puras
- `test_service.py`: os 5 cenários do desafio com scraper simulado + roteamento API/navegador
- `test_portal_api.py`: cliente da API oficial (APIRequestContext real do Playwright) contra uma API simulada local
- `test_api.py`: contrato HTTP, validação, API key, Swagger
- `test_e2e_mock.py`: **Chromium real** contra um portal simulado local, 4 consultas em paralelo

## Configuração (variáveis de ambiente)

| Variável | Padrão | Descrição |
|---|---|---|
| `API_KEY` | — | Se definida, exige header `X-API-Key` |
| `PORTAL_API_KEY` | — | Chave da API oficial; ativa CPF/NIS via API |
| `PORTAL_API_TIMEOUT_S` | 30 | Timeout por chamada à API oficial |
| `PORTAL_API_MAX_PAGINAS` | 3 | Páginas (15 registros cada) por benefício |
| `MAX_CONCURRENT_BOTS` | 3 | Robôs simultâneos |
| `HEADLESS` | true | Modo sem interface |
| `NAVIGATION_TIMEOUT_MS` | 30000 | Timeout de navegação |
| `SEARCH_TIMEOUT_MS` | 20000 | Timeout da busca |
| `TOTAL_TIMEOUT_S` | 120 | Timeout total por consulta |
| `SAVE_OUTPUT_FILES` | true | Salva JSON em `OUTPUT_DIR` |
| `CHROMIUM_EXECUTABLE_PATH` | — | Usa um Chrome/Chromium já instalado |

## Manutenção

Se o portal mudar o layout, ajuste **apenas** `app/bot/selectors.py`. Os scripts
de extração são genéricos (pares rótulo/valor e tabelas), o que reduz quebras.

## Parte 2 — Hiperautomação

🚧 **Em desenvolvimento.** O documento abaixo descreve o plano de implementação com Activepieces:
[docs/PARTE2_ACTIVEPIECES.md](docs/PARTE2_ACTIVEPIECES.md).

## Autor

**Igor Honorato** — [LinkedIn](https://www.linkedin.com/in/igor-honorato-martins/)

Desenvolvido com apoio do Claude Code (assistente de IA) na escrita e revisão do código; as decisões técnicas e os desafios estão documentados no [Relatório](RELATORIO.md).
