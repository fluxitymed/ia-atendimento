# Evolution API Sandbox

Esta feature usa a Evolution API apenas como provider WhatsApp de sandbox.
Nao use paciente real, nao comite `.env`, API key, QR Code, sessoes ou tokens.

## Variaveis

Preencha localmente:

```text
WHATSAPP_PROVIDER=evolution
EVOLUTION_API_BASE_URL=
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE_NAME=
EVOLUTION_WEBHOOK_SECRET=
EVOLUTION_PUBLIC_WEBHOOK_URL=
EVOLUTION_ORGANIZATION_ID=sandbox-org-aurora
```

## Comandos

Iniciar webhook local:

```bash
PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.evolution_server
```

Ver plano/smoke sem chamada real:

```bash
PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.evolution_sandbox smoke
```

Consultar estado da instancia:

```bash
PYTHONPATH=src RUN_EVOLUTION_LIVE=true python3 -m ai_agent_runtime.whatsapp.evolution_sandbox status
```

Criar instancia:

```bash
PYTHONPATH=src RUN_EVOLUTION_LIVE=true python3 -m ai_agent_runtime.whatsapp.evolution_sandbox create-instance
```

Obter QR Code/conectar:

```bash
PYTHONPATH=src RUN_EVOLUTION_LIVE=true python3 -m ai_agent_runtime.whatsapp.evolution_sandbox connect
```

Registrar webhook:

```bash
PYTHONPATH=src RUN_EVOLUTION_LIVE=true python3 -m ai_agent_runtime.whatsapp.evolution_sandbox set-webhook
```

## Webhook

Configure na Evolution:

```text
<EVOLUTION_PUBLIC_WEBHOOK_URL>/webhooks/evolution/whatsapp
```

Inclua o header:

```text
x-evolution-webhook-secret: <EVOLUTION_WEBHOOK_SECRET>
```

Eventos esperados: `MESSAGES_UPSERT`, `MESSAGES_UPDATE`, `SEND_MESSAGE`, `CONNECTION_UPDATE`, `QRCODE_UPDATED`.
