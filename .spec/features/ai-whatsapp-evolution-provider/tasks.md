# Tasks: AI WhatsApp Evolution Provider

> feature: ai-whatsapp-evolution-provider

## T-001 — Especificar provider Evolution [concluida]

- Refs: US-050, US-051, US-052, US-053, US-054, US-055, AC-156, AC-157, AC-158, AC-159, AC-160, AC-161, AC-162, AC-163, AC-164, AC-165, AC-166, AC-167, AC-168, AC-169, AC-170, AC-171, AC-172, AC-173, AC-174, AC-175, AC-176
- Arquivos: .spec/features/ai-whatsapp-evolution-provider/spec.md, .spec/features/ai-whatsapp-evolution-provider/tasks.md
- Notas: Documentacao oficial Evolution API consultada antes da implementacao.

## T-002 — Implementar configuracao, provider e factory Evolution [concluida]

- Refs: AC-156, AC-157, AC-158, AC-159, AC-160, AC-169, AC-170, AC-171, AC-174, AC-175
- Arquivos: .env.example, src/ai_agent_runtime/whatsapp/evolution.py, src/ai_agent_runtime/whatsapp/providers.py, src/ai_agent_runtime/whatsapp/__init__.py, test/ai-whatsapp-evolution-provider/evolution-provider.test.js
- Notas: Transport injetavel; nao remover provider Meta.

## T-003 — Implementar webhook Evolution e normalizacao de eventos [concluida]

- Refs: AC-161, AC-162, AC-163, AC-164, AC-165, AC-166, AC-167, AC-168, AC-176
- Arquivos: src/ai_agent_runtime/whatsapp/evolution_webhook.py, src/ai_agent_runtime/whatsapp/evolution_server.py, test/ai-whatsapp-evolution-provider/evolution-webhook.test.js
- Notas: Endpoint `/webhooks/evolution/whatsapp`; controller fino delega ao adapter.

## T-004 — Implementar smoke e guia operacional Evolution [concluida]

- Refs: AC-169, AC-170, AC-171, AC-172, AC-173, AC-174
- Arquivos: src/ai_agent_runtime/whatsapp/evolution_sandbox.py, .spec/features/ai-whatsapp-evolution-provider/evolution-sandbox.md, test/ai-whatsapp-evolution-provider/evolution-sandbox.test.js
- Notas: Offline nao depende de Evolution real; comandos devem ser seguros e sem secrets.

## T-005 — Validar regressao, verify e audit ONP [concluida]

- Refs: AC-156, AC-176
- Arquivos: .spec/features/ai-whatsapp-evolution-provider/tasks.md, .spec/verification/ai-whatsapp-evolution-provider.json
- Notas: Rodar suite, verify e audit; parar antes de teste real sem credenciais/URL publica.
