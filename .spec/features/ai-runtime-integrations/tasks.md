# Tasks — ai-runtime-integrations

## T-001 — Configuracao e schema Supabase [concluida]

- Refs: AC-049, AC-050, AC-051, AC-052, AC-053
- Arquivos: .env.example, supabase/migrations/202608200001_ai_runtime_integrations.sql, src/ai_agent_runtime/integrations/__init__.py, src/ai_agent_runtime/integrations/config.py, test/ai-runtime-integrations/integrations.test.js

Criar configuracao por ambiente e migration inicial com pgvector, entidades documentais, conversacionais, auditoria e constraints de organizacao.

## T-002 — Retrieval Supabase hibrido e elegivel [concluida]

- Refs: AC-054, AC-055, AC-056
- Arquivos: src/ai_agent_runtime/integrations/supabase_retrieval.py, test/ai-runtime-integrations/integrations.test.js

Implementar provider de retrieval com lexical + vector, isolamento por organizacao, elegibilidade documental e grounding obrigatorio.

## T-003 — OpenAI Responses e embeddings [concluida]

- Refs: AC-057, AC-058, AC-059, AC-060, AC-061
- Arquivos: src/ai_agent_runtime/integrations/openai_provider.py, test/ai-runtime-integrations/integrations.test.js

Implementar OpenAI provider com Responses API, `gpt-5.6-luna`, structured outputs, falhas controladas e embeddings rastreaveis.

## T-004 — LangSmith com redaction e auditoria local [concluida]

- Refs: AC-062, AC-063
- Arquivos: src/ai_agent_runtime/integrations/langsmith_observer.py, test/ai-runtime-integrations/integrations.test.js

Implementar observer opcional para LangSmith com redaction e sem alterar comportamento do dominio quando externo falhar.

## T-005 — Google Calendar provider guardado [concluida]

- Refs: AC-064, AC-065, AC-066
- Arquivos: src/ai_agent_runtime/integrations/google_calendar.py, test/ai-runtime-integrations/integrations.test.js

Implementar `CalendarProvider` para Google Calendar atras da interface existente, preservando guarda `SCHEDULING_CONTEXT_ACTIVE` antes de chamada externa.
