# Tasks: AI CRM Conversation Runtime

> feature: ai-crm-conversation-runtime

## T-075 — Especificar contrato CRM e arquitetura [concluida]
- Refs: US-108, US-109, US-110, US-111, US-112, AC-457, AC-458, AC-459, AC-460, AC-461, AC-462, AC-463, AC-464, AC-465, AC-466, AC-467, AC-468, AC-469, AC-470, AC-471, AC-472, AC-473, AC-474, AC-475, AC-476
- Arquivos: .spec/features/ai-crm-conversation-runtime/spec.md, .spec/features/ai-crm-conversation-runtime/tasks.md, .spec/features/ai-crm-conversation-runtime/design.md
- Modelo: gpt-5.6-terra
- Esforco: alto
- Notas: Execucao sequencial confirmada pelo usuario; separar IDs e credenciais do CRM dos IDs e credenciais da IA/RAG.

## T-076 — Criar testes do repositorio CRM [concluida]
- Refs: US-108, US-110, US-111, US-112, AC-457, AC-458, AC-459, AC-460, AC-467, AC-468, AC-469, AC-470, AC-472, AC-473, AC-474, AC-475
- Arquivos: test/ai-crm-conversation-runtime/crm-conversation-runtime.test.js
- Modelo: gpt-5.6-terra
- Esforco: alto
- Notas: Cobrir transporte REST injetavel, idempotencia, lifecycle, mapping cross-org e sanitizacao antes da implementacao.

## T-077 — Implementar repositorio e monitor CRM [concluida]
- Refs: US-108, US-110, US-111, US-112, AC-457, AC-458, AC-459, AC-460, AC-467, AC-468, AC-469, AC-470, AC-472, AC-473, AC-474, AC-475
- Arquivos: src/ai_agent_runtime/integrations/crm_conversations.py, src/ai_agent_runtime/integrations/config.py, src/ai_agent_runtime/integrations/__init__.py, .env.example
- Modelo: gpt-5.6-terra
- Esforco: alto
- Notas: Usar apenas `CRM_SUPABASE_*`; nenhuma credencial em logs; contact_id nulo.

## T-078 — Integrar gate e lifecycle ao adapter Z-API [concluida]
- Refs: US-109, US-110, US-111, AC-461, AC-462, AC-463, AC-464, AC-465, AC-466, AC-467, AC-468, AC-469, AC-470, AC-471, AC-472
- Arquivos: src/ai_agent_runtime/whatsapp/adapter.py, src/ai_agent_runtime/whatsapp/channel.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Modelo: gpt-5.6-terra
- Esforco: alto
- Notas: Trabalhar sobre mudancas nao commitadas existentes; consultar CRM em cada inbound e retornar sucesso fail-closed sem outbound.

## T-079 — Verificar regressoes e fechar gate [concluida]
- Refs: US-112, AC-476
- Arquivos: test/ai-crm-conversation-runtime/crm-conversation-runtime.test.js, test/ai-whatsapp-zapi-provider, test/ai-customer-service, .spec/verification/ai-crm-conversation-runtime.json
- Modelo: gpt-5.6-terra
- Esforco: alto
- Notas: Rodar compileall, toda suite Node, verify da feature e audit --ci.
