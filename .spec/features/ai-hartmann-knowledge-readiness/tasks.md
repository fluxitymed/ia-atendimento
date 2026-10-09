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

## T-103 — Corrigir turno comercial com preco e agendamento [concluida]
- Refs: US-121, AC-536, AC-537, AC-538, AC-539
- Arquivos: .spec/features/ai-hartmann-knowledge-readiness/spec.md, .spec/features/ai-hartmann-knowledge-readiness/design.md, .spec/features/ai-hartmann-knowledge-readiness/tasks.md, .spec/features/ai-hartmann-knowledge-readiness/verification.md, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/crm_dispatch.py, test/ai-hartmann-knowledge-readiness/multi-intent.test.js, test/ai-hartmann-knowledge-readiness/dispatch-observability.test.js
- Notas: Reservar evidencia de cada assunto antes de preencher o limite, validar afirmacoes independentes contra fontes distintas e separar no log a existencia de candidatos do veredito do grounding. Preservar os dois testes preexistentes unstaged de ai-knowledge-crm-api.

## T-104 — Diagnosticar cobertura e proteger origem da falha comercial [concluida]
- Refs: US-122, AC-540, AC-541, AC-542, AC-543
- Arquivos: .spec/features/ai-hartmann-knowledge-readiness/spec.md, .spec/features/ai-hartmann-knowledge-readiness/design.md, .spec/features/ai-hartmann-knowledge-readiness/tasks.md, .spec/features/ai-hartmann-knowledge-readiness/verification.md, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/crm_dispatch.py, test/ai-hartmann-knowledge-readiness/commercial-diagnostics.test.js, test/ai-hartmann-knowledge-readiness/dispatch-observability.test.js
- Notas: Usar o listener e os eventos CRM existentes. Cobertura lexical e apenas candidato, nunca prova factual. Conservar HANDOFF quando a origem da afirmacao nao puder ser demonstrada; preservar alteracoes preexistentes de test/ai-knowledge-crm-api/.
