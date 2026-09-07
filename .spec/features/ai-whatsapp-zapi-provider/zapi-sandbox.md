# Z-API Sandbox

> feature: ai-whatsapp-zapi-provider

## Objetivo

Validar conversas comerciais reais da IA usando Z-API como provider temporario de sandbox/MVP. A Z-API opera sessao de WhatsApp Web e nao representa a infraestrutura definitiva de producao.

## Variaveis

Preencher localmente, sem commitar secrets:

```text
WHATSAPP_PROVIDER=zapi
ZAPI_BASE_URL=https://api.z-api.io
ZAPI_INSTANCE_ID=
ZAPI_INSTANCE_TOKEN=
ZAPI_CLIENT_TOKEN=
ZAPI_PUBLIC_WEBHOOK_URL=
ZAPI_ORGANIZATION_ID=sandbox-org-dr-leonardo-carvalho
ZAPI_STORE_PATH=.sandbox/zapi-whatsapp-store.json
```

## Webhook

Endpoint local implementado:

```text
POST /webhooks/zapi/whatsapp
```

A URL publica HTTPS a configurar no painel/API da Z-API deve apontar para:

```text
<ZAPI_PUBLIC_WEBHOOK_URL>/webhooks/zapi/whatsapp
```

A documentacao oficial da Z-API para `on-message-received` configura apenas a URL HTTPS de callback e nao documenta secret, signature ou header custom verificavel no POST recebido. Por isso, o endpoint local nao rejeita callbacks legitimos por ausencia de `ZAPI_WEBHOOK_SECRET`.

O contrato de seguranca inbound fica em:

- URL publica HTTPS configurada somente na instancia sandbox;
- `instanceId` do payload precisa estar vinculado a uma organizacao conhecida;
- `organizationId` vindo do payload/conteudo do paciente e ignorado;
- unknown instance recebe 403;
- idempotencia, ordering e self-message protection continuam no adapter;
- payload invalido ou tipo nao suportado recebe 400.

## Comandos

Iniciar servidor local:

```bash
PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.zapi_server
```

Ver plano/smoke sem chamadas reais:

```bash
PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.zapi_sandbox smoke
```

Consultar status real da instancia:

```bash
PYTHONPATH=src RUN_ZAPI_LIVE=true python3 -m ai_agent_runtime.whatsapp.zapi_sandbox status
```

Obter QR Code real, quando aplicavel:

```bash
PYTHONPATH=src RUN_ZAPI_LIVE=true python3 -m ai_agent_runtime.whatsapp.zapi_sandbox qr-code
```

Configurar webhook recebido na Z-API:

```bash
PYTHONPATH=src RUN_ZAPI_LIVE=true python3 -m ai_agent_runtime.whatsapp.zapi_sandbox set-webhook
```

## Cenarios live esperados

- validar configuracao;
- verificar status da instancia;
- obter QR Code/conexao quando aplicavel;
- configurar webhook recebido;
- testar outbound text;
- validar inbound text real;
- validar inbound audio real;
- validar inbound image real;
- validar inbound document real;
- validar duplicate webhook;
- validar self-message;
- validar handoff;
- validar scheduling sem inventar disponibilidade.

`LIVE_VERIFIED` so pode ser usado apos chamadas reais de status, webhook, outbound e inbound no sandbox. Sem credenciais ou sem execucao opt-in, o estado deve permanecer `BLOCKED_MISSING_CREDENTIALS` ou `READY_FOR_LIVE_EXECUTION`.
