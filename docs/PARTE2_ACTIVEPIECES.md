# Parte 2 — Workflow de Hiperautomação (Activepieces)

## Por que Activepieces

- **Open source** e com free tier na nuvem; pode ser self-hosted (Docker) se a
  empresa quiser manter dados internamente — relevante para dados pessoais (LGPD).
- Peças nativas de Google Drive e Google Sheets com **OAuth 2.0** (nenhuma
  credencial Google fica no código).
- Passo de **código em TypeScript** para transformações pontuais.
- Sem limite agressivo de operações como Zapier free (100 tasks/mês).

## Pré-requisitos

1. API publicada (ver "Deploy" abaixo) com `API_KEY` definida.
2. Pasta no Google Drive, ex.: `Consultas Portal Transparência`.
3. Planilha no Google Sheets com a aba `Registro` e o cabeçalho:

| A | B | C | D | E | F | G | H | I |
|---|---|---|---|---|---|---|---|---|
| ID Consulta | Nome | CPF | Termo Pesquisado | Filtro Social | Data/Hora | Status | Mensagem | Link JSON |

## Fluxo

```
[1 Webhook] → [2 HTTP POST robô] → [3 Code: preparar JSON] → [4 Drive: criar arquivo]
           → [5 Sheets: inserir linha] → [6 Router: erro? → notificação] → [7 Resposta do webhook]
```

### 1. Trigger — Webhook (Catch Webhook)
Corpo esperado:
```json
{ "termo": "MARIA DA SILVA", "filtro_beneficiario_programa_social": false }
```
Alternativa: trigger **Google Sheets → New Row** numa aba "Solicitações", para
que usuários de negócio disparem consultas digitando na planilha.

### 2. HTTP — Send HTTP Request
- Method: `POST`
- URL: `https://SEU-SERVICO/api/v1/consultas`
- Headers: `X-API-Key` = valor guardado como *secret/connection* (não fixar no texto)
- Body (JSON): `{{trigger.body}}`
- Timeout: 300 s

### 3. Code — preparar conteúdo
```typescript
export const code = async (inputs: { resposta: any }) => {
  const r = inputs.resposta;
  return {
    nome_arquivo: r.nome_arquivo,                     // [ID]_[DATA_HORA].json
    conteudo: JSON.stringify(r, null, 2),
    nome: r.dados?.nome ?? '',
    cpf: r.dados?.cpf ?? '',
  };
};
```
Input `resposta` = `{{step_2.body}}`.

### 4. Google Drive — Create new text file
- Connection: OAuth Google
- File name: `{{step_3.nome_arquivo}}`
- Text: `{{step_3.conteudo}}`
- Content type: `application/json`
- Parent folder: pasta criada nos pré-requisitos

### 5. Google Sheets — Insert Row
| Coluna | Valor |
|---|---|
| ID Consulta | `{{step_2.body.id_consulta}}` |
| Nome | `{{step_3.nome}}` |
| CPF | `{{step_3.cpf}}` |
| Termo Pesquisado | `{{step_2.body.parametros.termo}}` |
| Filtro Social | `{{step_2.body.parametros.filtro_beneficiario_programa_social}}` |
| Data/Hora | `{{step_2.body.data_hora_consulta}}` |
| Status | `{{step_2.body.status}}` |
| Mensagem | `{{step_2.body.mensagem}}` |
| Link JSON | `https://drive.google.com/file/d/{{step_4.id}}/view` |

### 6. Router (bônus — notificação)
Se `{{step_2.body.status}}` = `erro` → Gmail/Slack/Telegram com ID, termo e mensagem.

### 7. Return Response (webhook)
```json
{ "id_consulta": "{{step_2.body.id_consulta}}", "status": "{{step_2.body.status}}",
  "link_json": "https://drive.google.com/file/d/{{step_4.id}}/view" }
```

> Os nomes exatos dos campos de saída (ex.: `step_4.id`) podem variar conforme a
> versão da peça; confira na aba de dados de teste de cada passo.

## Deploy da API (online para testes)

Recomendado: **Google Cloud Run** (free tier generoso, aceita Dockerfile, memória
configurável e timeout de requisição longo).

```bash
gcloud run deploy robo-portal-transparencia --source . --region southamerica-east1 \
  --memory 2Gi --cpu 2 --timeout 300 --max-instances 2 --concurrency 4 \
  --set-env-vars MAX_CONCURRENT_BOTS=3 --set-secrets API_KEY=robo-api-key:latest \
  --allow-unauthenticated
```

Alternativas: Render (free tier com 512 MB — use `MAX_CONCURRENT_BOTS=1` ou `2`
e considere o *cold start*) ou Railway.
