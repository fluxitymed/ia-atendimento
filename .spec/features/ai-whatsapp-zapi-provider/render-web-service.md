# Render Web Service — Z-API Sandbox

Este guia prepara o servidor Z-API para rodar 24/7 em um Render Web Service, sem depender do Mac local nem de Cloudflare Tunnel.

## Configuracao do servico

- **Runtime:** Python
- **Start command:** `PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.zapi_server`
- **Health check path:** `/health`
- **Bind:** o servidor usa `0.0.0.0` e respeita `PORT` quando o Render injeta essa variavel.

## Persistent Disk

Monte um Persistent Disk no Render em:

```text
/var/data
```

Configure:

```text
ZAPI_STORE_PATH=/var/data/zapi-whatsapp-store.json
```

O servidor cria o diretorio e o arquivo JSON quando necessario. Em `APP_ENV=production` ou no ambiente Render, se `ZAPI_STORE_PATH` nao estiver definido, o fallback tambem e `/var/data/zapi-whatsapp-store.json`.

## Kill switch

Use:

```text
AI_INBOUND_ENABLED=true
```

Quando `AI_INBOUND_ENABLED=false`, o webhook continua aceitando callbacks validos, registra idempotencia e gera o log `ai_inbound_disabled`, mas nao executa runtime da IA e nao envia outbound automatico.

## Variaveis para copiar ao Render

Copie apenas os nomes abaixo e preencha no painel do Render, sem commitar valores:

```text
APP_ENV
AI_INBOUND_ENABLED
PYTHONPATH
WHATSAPP_PROVIDER
ZAPI_BASE_URL
ZAPI_INSTANCE_ID
ZAPI_INSTANCE_TOKEN
ZAPI_CLIENT_TOKEN
ZAPI_PUBLIC_WEBHOOK_URL
ZAPI_ORGANIZATION_ID
ZAPI_STORE_PATH
MESSAGE_BATCH_ENABLED
MESSAGE_BATCH_DEBOUNCE_MS
MESSAGE_BATCH_MAX_WAIT_MS
AUDIO_INBOUND_ENABLED
AUDIO_MAX_BYTES
AUDIO_DOWNLOAD_TIMEOUT_SECONDS
AUDIO_STT_MAX_ATTEMPTS
OPENAI_API_KEY
OPENAI_RESPONSES_MODEL
OPENAI_REASONING_EFFORT
OPENAI_EMBEDDING_MODEL
OPENAI_STT_MODEL
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
LANGSMITH_API_KEY
LANGSMITH_ENDPOINT
LANGSMITH_PROJECT
GOOGLE_CALENDAR_ID
GOOGLE_CALENDAR_ACCESS_TOKEN
GOOGLE_CALENDAR_REFRESH_TOKEN
GOOGLE_CALENDAR_TIMEZONE
GOOGLE_OAUTH_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET
GOOGLE_OAUTH_TOKEN_URI
AI_ASSISTANT_NAME
AI_ASSISTANT_ROLE
AI_CLINIC_NAME
AI_DOCTOR_NAME
AI_ASSISTANT_TONE
AI_SALES_GOAL
AI_PRIMARY_CONVERSION_ACTION
AI_MAX_DISCOVERY_DEPTH
AI_CTA_STYLE
AI_APPOINTMENT_FLOW
AI_BUSINESS_HOURS
AI_LOCATIONS
```

`PORT` e fornecida pelo Render e nao precisa ser criada manualmente.

## Prova operacional

1. Crie o Web Service apontando para este repositorio.
2. Configure o start command.
3. Monte o Persistent Disk em `/var/data`.
4. Configure as variaveis de ambiente.
5. Configure na Z-API a URL publica HTTPS do Render para `POST /webhooks/zapi/whatsapp`.
6. Verifique `GET /health`.
7. Envie uma mensagem para a instancia Z-API e confirme logs `zapi_webhook_ingress_received`, `organization_resolved`, `conversation_resolved`, `runtime_started`, `response_generated` e `outbound_sent`.
