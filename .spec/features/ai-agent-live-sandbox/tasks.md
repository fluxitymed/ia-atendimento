# Tasks: AI Agent Live Sandbox

> feature: ai-agent-live-sandbox

## T-001 — Configurar ambiente sandbox e readiness de credenciais [concluida]
- Refs: US-030, AC-100, AC-101, AC-102, AC-103
- Arquivos: src/ai_agent_runtime/integrations/config.py, src/ai_agent_runtime/sandbox/config.py, src/ai_agent_runtime/sandbox/__init__.py, .env.example, test/ai-agent-live-sandbox/live-sandbox.test.js
- Notas: Nenhum segredo hard-coded; live bloqueado sem `APP_ENV=sandbox` e `RUN_LIVE_SANDBOX=true`.

## T-002 — Implementar runner e relatorio sandbox opt-in [concluida]
- Refs: US-031, AC-104, AC-105, AC-106
- Arquivos: src/ai_agent_runtime/sandbox/runner.py, src/ai_agent_runtime/sandbox/reporting.py, src/ai_agent_runtime/sandbox/__main__.py, test/ai-agent-live-sandbox/live-sandbox.test.js
- Notas: `python -m ai_agent_runtime.sandbox`; exit code adequado e status `IMPLEMENTED/BLOCKED/LIVE_VERIFIED`.

## T-003 — Preparar smoke OpenAI real sem executar por padrao [concluida]
- Refs: US-032, AC-107, AC-108
- Arquivos: src/ai_agent_runtime/sandbox/openai_smoke.py, test/ai-agent-live-sandbox/live-sandbox.test.js
- Notas: Responses API, Luna, structured output, usage quando disponivel e erro redigido.

## T-004 — Preparar Supabase sandbox e dataset ficticio [concluida]
- Refs: US-033, AC-109, AC-110, AC-111, AC-112
- Arquivos: src/ai_agent_runtime/sandbox/dataset.py, src/ai_agent_runtime/sandbox/supabase_smoke.py, test/ai-agent-live-sandbox/live-sandbox.test.js
- Notas: Clinica Aurora Sandbox, Clinica Boreal Sandbox, catalogo fechado e plano de gaps do pipeline.

## T-005 — Preparar grounding, prompt injection e Google Calendar sandbox [concluida]
- Refs: US-034, US-035, AC-113, AC-114, AC-115, AC-116, AC-117
- Arquivos: src/ai_agent_runtime/sandbox/scenarios.py, src/ai_agent_runtime/sandbox/google_calendar_smoke.py, test/ai-agent-live-sandbox/live-sandbox.test.js
- Notas: Agenda somente com `SCHEDULING_CONTEXT_ACTIVE`; evento sandbox com cleanup.

## T-006 — Preparar LangSmith, redaction e gate ONP [concluida]
- Refs: US-036, AC-118, AC-119
- Arquivos: src/ai_agent_runtime/sandbox/redaction.py, src/ai_agent_runtime/sandbox/langsmith_smoke.py, test/ai-agent-live-sandbox/live-sandbox.test.js
- Notas: Projeto `ai-atendimento-sandbox`, auditoria local preservada e relatorios sem secrets.

## T-007 — Criar utilitario OAuth local Google Calendar sandbox [concluida]
- Refs: US-037, AC-120, AC-121, AC-122, AC-123
- Arquivos: src/ai_agent_runtime/sandbox/google_oauth.py, src/ai_agent_runtime/integrations/config.py, .env.example, .gitignore, test/ai-agent-live-sandbox/live-sandbox.test.js
- Notas: Fluxo Desktop com loopback local, scopes `calendar.freebusy` e `calendar.events`, token file ignorado e output redigido.

## T-008 — Finalizar execucao live real das integracoes sandbox [concluida]
- Refs: US-033, US-035, US-036, AC-109, AC-110, AC-111, AC-112, AC-115, AC-116, AC-117, AC-118, AC-119
- Arquivos: src/ai_agent_runtime/sandbox/supabase_smoke.py, src/ai_agent_runtime/sandbox/google_calendar_smoke.py, src/ai_agent_runtime/sandbox/langsmith_smoke.py, src/ai_agent_runtime/sandbox/runner.py, src/ai_agent_runtime/integrations/google_calendar.py, src/ai_agent_runtime/integrations/config.py, .env.example, test/ai-runtime-integrations/integrations.test.js, test/ai-agent-live-sandbox/live-sandbox.test.js
- Notas: Runner live executa chamadas reais a OpenAI, Supabase, Google Calendar e LangSmith; refresh OAuth automatico testado offline; eventos sandbox sao removidos; traces LangSmith usam redaction e workspace resolvido sem imprimir secrets.
