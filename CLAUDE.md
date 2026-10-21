# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão geral

Robô em Python (FastAPI + Playwright async) que consulta **Pessoa Física** no Portal da Transparência, coleta o panorama + detalhes de benefícios, captura screenshot em Base64 e devolve JSON. O código, os nomes e as mensagens são em português — mantenha esse padrão.

## Comandos

```bash
pip install -r requirements-dev.txt
playwright install --with-deps chromium
cp .env.example .env

uvicorn app.main:app --reload                 # API; Swagger em http://localhost:8000/docs
python -m app.cli "MARIA DA SILVA"            # CLI (--filtro-social, --saida arq.json, --visivel)
python scripts/demo_concorrencia.py "MARIA DA SILVA" "SILVA:social" "00000000000"
docker compose up --build

pytest                                        # todos os testes (pytest.ini: testpaths=tests, -q)
pytest tests/test_service.py::test_sucesso_nome   # um teste
```

- Rode o Uvicorn com **um único worker**: a concorrência é por asyncio dentro do processo; vários workers criariam vários Chromium.
- `tests/test_e2e_mock.py` usa um Chromium real e é **pulado** se o navegador não puder ser iniciado. Use `CHROMIUM_EXECUTABLE_PATH` para apontar para um Chrome já instalado.
- Testes usam `asyncio.run(...)` diretamente (não há pytest-asyncio).

## Arquitetura

Fluxo de uma consulta: `api/routes.py` → `ConsultaService.executar` (`services/consulta_service.py`) → **API oficial** (`bot/portal_api.py`) ou **navegador** (`bot/portal_scraper.py`) → `ConsultaResponse` (`schemas.py`) → JSON salvo em `output/[id]_[YYYYmmdd_HHMMSS].json`.

- **Ciclo de vida** (`app/main.py`, `lifespan`): cria um `BrowserManager`, opcionalmente um `PortalApiClient` (só se `PORTAL_API_KEY` estiver definida) e o `ConsultaService`, guardados em `app.state`. As rotas obtêm o service via `request.app.state.service`.
- **Roteamento de fonte**: `classificar_termo` (`utils/validators.py`) detecta NOME/CPF/NIS com validação de dígitos. CPF/NIS vão para a API oficial se houver cliente; **nome sempre vai pelo navegador** (a API oficial não busca por nome). O campo `fonte` da resposta é `api_oficial` ou `navegador`; pela API não há screenshot (`evidencia_base64 = null`).
- **Concorrência** (`bot/browser.py`): um único processo Chromium compartilhado, um `BrowserContext` isolado por consulta, limitado por `asyncio.Semaphore(MAX_CONCURRENT_BOTS)`. O Chromium é relançado automaticamente se cair. `PortalApiClient` reusa a mesma instância Playwright (`APIRequestContext`), então todo HTTP passa pelo Playwright.
- **Erros**: exceções de domínio em `bot/exceptions.py`, cada uma com `codigo` (`NENHUM_RESULTADO`, `TEMPO_ESGOTADO`, `PORTAL_INDISPONIVEL`, `BLOQUEIO_ANTIBOT`) e `evidencia_base64` opcional. `mensagem_de_erro` no service as traduz para as mensagens exatas exigidas pelo desafio — ex.: CPF/NIS inexistente retorna a mensagem de *tempo esgotado*, não a de 0 resultados. Toda exceção vira resposta JSON; o service nunca propaga erro.
- **HTTP 200 para erros de negócio** (`status: "erro"`) é intencional: ferramentas de workflow (ActivePieces, ver `docs/PARTE2_ACTIVEPIECES.md`) interrompem o fluxo em não-2xx. Só validação (422) e API key (401) usam outros códigos.
- **Scraper**: busca → abre o primeiro resultado → panorama (expande acordeões) → screenshot → abre cada link "Detalhar" em nova página. Falha em um detalhe de benefício não derruba a consulta (vira `observacao` com dados parciais). Timeout global por consulta via `asyncio.wait_for(TOTAL_TIMEOUT_S)`.
- **`bot/selectors.py` é o único lugar que conhece o HTML do portal** (seletores CSS + scripts JS genéricos de rótulo/valor e tabelas). Se o layout mudar, ajuste só esse arquivo. `bot/parsers.py` contém funções puras de normalização; a saída da API oficial é achatada (`achatar`, camelCase → snake_case, valores em BRL) para ter o mesmo formato das tabelas do scraper.
- **LGPD**: documentos são mascarados em logs com `mascarar_documento`.
- **Configuração**: `core/config.py` (`pydantic-settings`, lê `.env`, `get_settings()` com `lru_cache`). Nos testes, instancie `Settings(...)` diretamente com overrides (ex.: `save_output_files=False`).

## Testes e injeção de dependências

- `ConsultaService` aceita `scraper_cls` e `api` injetáveis; `tests/test_service.py` usa `FakeBrowser`/`FakeScraper`/`FakeApi` para cobrir os 5 cenários do desafio sem navegador.
- `tests/test_e2e_mock.py` sobe um `ThreadingHTTPServer` servindo `tests/fixtures/portal_mock/` (arquivos **sem extensão**, servidos como `text/html`, espelhando os caminhos de URL do portal) e roda 4 consultas em paralelo com `portal_base_url` apontando para ele. Ao mudar seletores ou o fluxo do scraper, atualize essas fixtures.
- `tests/test_portal_api.py` testa o cliente da API oficial com um `APIRequestContext` real contra uma API simulada local.
