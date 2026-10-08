# Tarefas — RAG multi-tenant Hartmann

> feature: ai-hartmann-knowledge-readiness

## T-087 — Auditar schema e contratos [concluida]

- Refs: US-115, AC-494, AC-495
- Arquivos: .spec/features/ai-hartmann-knowledge-readiness/design.md

## T-088 — Corrigir elegibilidade e vinculos no retrieval [concluida]

- Refs: AC-494, AC-495, AC-496, AC-497, AC-498
- Arquivos: src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-hartmann-knowledge-readiness/rag-readiness.test.js, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js

## T-089 — Validar grounding e cache [concluida]

- Refs: US-116, AC-499
- Arquivos: src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-hartmann-knowledge-readiness/rag-readiness.test.js

## T-090 — Documentar carga operacional e verificar [concluida]

- Refs: US-115, US-116, AC-494, AC-499
- Arquivos: .spec/features/ai-hartmann-knowledge-readiness/design.md, .spec/features/ai-hartmann-knowledge-readiness/spec.md

## T-102 — Rastrear a decisao CRM e fechar correcoes comerciais [concluida]
- Refs: US-116, US-120, AC-499, AC-533, AC-534, AC-535
- Arquivos: .spec/features/ai-hartmann-knowledge-readiness/spec.md, .spec/features/ai-hartmann-knowledge-readiness/design.md, .spec/features/ai-hartmann-knowledge-readiness/tasks.md, .spec/features/ai-hartmann-knowledge-readiness/verification.md, onpspec.config.json, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/crm_dispatch.py, test/ai-hartmann-knowledge-readiness/rag-readiness.test.js, test/ai-hartmann-knowledge-readiness/dispatch-observability.test.js, test/ai-hartmann-knowledge-readiness/commercial-scenarios.test.js
- Notas: Reutilizar os eventos do grafo no listener CRM existente; emitir apenas resumo terminal com campos permitidos. Nao registrar mensagens, prompts, conteudo de chunks, respostas do modelo ou segredos. Preservar a correcao local do retrieval e grounding.
