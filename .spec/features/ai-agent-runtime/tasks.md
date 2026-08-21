# Tasks — ai-agent-runtime

## T-001 — Implementar estado, intencao e graph runtime [concluida]

- Refs: AC-033, AC-034, AC-047, AC-048
- Arquivos: src/ai_agent_runtime/state.py, src/ai_agent_runtime/graph.py, src/ai_agent_runtime/__init__.py, test/ai-agent-runtime/runtime.test.js

Implementar estado conversacional, intencoes, estagios, grafo com nodes separados e fluxo de handoff sem depender de WhatsApp.

## T-002 — Implementar providers e guardas de agenda [concluida]

- Refs: AC-035, AC-036, AC-037, AC-038, AC-039
- Arquivos: src/ai_agent_runtime/providers.py, src/ai_agent_runtime/scheduling.py, test/ai-agent-runtime/runtime.test.js

Implementar `CalendarProvider`, tools de agenda e guarda deterministica para impedir disponibilidade fora de `SCHEDULING_CONTEXT_ACTIVE`.

## T-003 — Implementar CRM progressivo [concluida]

- Refs: AC-040, AC-041
- Arquivos: src/ai_agent_runtime/providers.py, src/ai_agent_runtime/crm.py, test/ai-agent-runtime/runtime.test.js

Implementar `CRMProvider` e atualizacao progressiva sem inventar campos ausentes.

## T-004 — Implementar retrieval hibrido e grounding gate [concluida]

- Refs: AC-042, AC-043, AC-044
- Arquivos: src/ai_agent_runtime/retrieval.py, src/ai_agent_runtime/grounding.py, test/ai-agent-runtime/runtime.test.js

Implementar portas para busca lexical e vetorial, fusao hibrida isolada por organizacao e gate de grounding antes de resposta factual.

## T-005 — Implementar auditoria operacional e observabilidade opcional [concluida]

- Refs: AC-045, AC-046
- Arquivos: src/ai_agent_runtime/observability.py, test/ai-agent-runtime/runtime.test.js

Implementar eventos de auditoria de negocio independentes de LangSmith e observador opcional.
