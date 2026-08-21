# Tasks: AI Agent Evaluation

> feature: ai-agent-evaluation

## T-001 — Criar modelo e runner offline de avaliacao [concluida]
- Refs: US-022, AC-067, AC-068, AC-069
- Arquivos: src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/runner.py, src/ai_agent_runtime/evaluation/__init__.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Framework deterministico sem chamadas externas.

## T-002 — Calcular metricas e gate de tolerancia zero [concluida]
- Refs: US-023, AC-070, AC-071
- Arquivos: src/ai_agent_runtime/evaluation/metrics.py, src/ai_agent_runtime/evaluation/reporting.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Aprovar somente quando metricas criticas permanecerem em zero.

## T-003 — Criar dataset ficticio de cenarios RAG e catalogo [concluida]
- Refs: US-024, US-025, AC-072, AC-073, AC-074, AC-075, AC-076, AC-077, AC-078, AC-079
- Arquivos: src/ai_agent_runtime/evaluation/dataset.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Cobrir informacao presente, parcial, inexistente, conhecimento medico, closed-world e matching aproximado.

## T-004 — Cobrir semantica, conflito, elegibilidade e ataques de grounding [concluida]
- Refs: US-026, US-027, AC-080, AC-081, AC-082, AC-083, AC-084, AC-085, AC-086, AC-087, AC-088
- Arquivos: src/ai_agent_runtime/evaluation/dataset.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Incluir negacoes, excecoes, conflito, documentos inelegiveis, cross-org e prompt injection.

## T-005 — Cobrir agenda, tool guard e disponibilidade [concluida]
- Refs: US-028, AC-089, AC-090, AC-091, AC-092, AC-093
- Arquivos: src/ai_agent_runtime/evaluation/dataset.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Usar provider fake e tentativas simuladas de tool fora de contexto.

## T-006 — Cobrir CRM progressivo, handoff e conversa longa [concluida]
- Refs: US-029, AC-094, AC-095, AC-096, AC-097, AC-098, AC-099
- Arquivos: src/ai_agent_runtime/evaluation/dataset.py, src/ai_agent_runtime/evaluation/reporting.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Garantir que dados ficticios e contexto sejam preservados sem invencao.
