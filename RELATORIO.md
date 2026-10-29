# Relatório Técnico

## 1. Decisões técnicas

**Playwright (async) em vez de Selenium.** Espera automática por elementos,
API assíncrona nativa (essencial para execuções simultâneas num único processo),
headless estável e imagem Docker oficial com o navegador já instalado.

**Um navegador, vários contextos.** Abrir um Chromium por consulta custa ~150–300 MB
e alguns segundos. Compartilho um único Chromium e crio um `BrowserContext` por
consulta — isolamento total de cookies/sessão a uma fração do custo. Um semáforo
(`MAX_CONCURRENT_BOTS`) limita o paralelismo e as demais consultas aguardam na fila,
protegendo memória e evitando bloqueio por excesso de requisições ao portal.

**Busca pela URL da consulta em vez de digitar no formulário.** A tela de
"Pessoas Físicas" aceita os mesmos parâmetros do formulário na URL
(`termo`, `beneficiarioProgramaSocial`). Isso elimina etapas frágeis
(cliques em acordeão de filtro, digitação) e torna o robô determinístico.

**Seletores isolados e extração genérica.** Todo conhecimento do HTML está em
`selectors.py`. A extração lê pares rótulo/valor e tabelas de forma genérica,
então novos campos ou benefícios aparecem no JSON sem alterar código.

**Resiliência.** Timeout por etapa e timeout global; falha no detalhe de um
benefício não derruba a consulta (retorna dados parciais com observação);
reconexão automática se o Chromium cair; evidência capturada também em erros.

**Contrato de erro amigável a workflows.** Erros de negócio retornam HTTP 200 com
`status: "erro"`, `codigo_erro` e `mensagem` exatamente como pedido nos cenários.

**Segurança.** Configuração por variáveis de ambiente, `.env` fora do Git,
API key comparada em tempo constante, container com usuário não-root, CPF
mascarado nos logs (LGPD), credenciais Google apenas via OAuth 2.0 na plataforma
de workflow.

## 2. Desafios enfrentados

- **Conteúdo carregado via JavaScript:** a busca e as tabelas de detalhe são
  preenchidas de forma assíncrona. Resolvido com `wait_for_function` aguardando
  condições reais (contador preenchido, linhas sem "Carregando…").
- **Diferenciar "não encontrado" de "lento":** cenários exigem mensagens
  diferentes para nome e documento; o serviço traduz exceções de domínio em
  mensagens conforme o tipo de termo.
- **CPF x NIS:** ambos têm 11 dígitos; a classificação usa os dígitos verificadores.
- **CAPTCHA em execuções simultâneas:** no teste real, 3 consultas pelo navegador
  disparadas juntas fizeram o portal exibir verificação humana em 2 delas; as mesmas
  consultas, uma de cada vez, funcionaram. Mitigação: início dos robôs espaçado,
  concorrência padrão 2 e nova tentativa automática com espera crescente (10s, 30s)
  num contexto limpo, sem estourar o timeout total. CPF/NIS pela API oficial não
  sofrem esse bloqueio — motivo central da fonte híbrida.
- **Headless x CAPTCHA:** em testes posteriores, o modo headless (inclusive o
  `--headless=new` do Chrome) passou a receber CAPTCHA mesmo em consultas isoladas,
  enquanto a mesma consulta com navegador visível passou em ~15s. Na execução local
  uso `HEADLESS=false`. Optei por não falsificar sinais do navegador para driblar a
  proteção do portal: para volume, o caminho legítimo é a API oficial.
- **Concorrência x memória:** o limite de robôs simultâneos é configurável para
  caber no free tier do provedor.
- **Testabilidade sem depender do portal:** criei um portal simulado local para
  rodar o robô real (Chromium) de ponta a ponta nos testes automatizados.

## 3. Plataforma da Parte 2

**Activepieces** — open source, self-hostable (dados pessoais podem ficar na
infraestrutura da empresa), peças nativas de Google Drive/Sheets com OAuth 2.0,
passo de código para transformações e free tier sem o limite baixo do Zapier.
Detalhes em `docs/PARTE2_ACTIVEPIECES.md`.

## 4. Melhorias futuras

Fila assíncrona (job + callback/webhook) para consultas longas, retry com
backoff para instabilidades do portal, métricas (Prometheus), cache de consultas
recentes e monitoramento sintético para detectar mudança de layout.
