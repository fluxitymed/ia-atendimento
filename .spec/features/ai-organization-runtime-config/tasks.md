# Tasks: ai-organization-runtime-config

> feature: ai-organization-runtime-config

## T-069 — Especificar contratos multi-tenant de runtime [concluida]
- Refs: US-101, US-102, US-103, US-104, US-105, AC-421, AC-422, AC-423, AC-424, AC-425, AC-426, AC-427, AC-428, AC-429, AC-430, AC-431, AC-432, AC-433, AC-434, AC-435
- Arquivos: .spec/features/ai-organization-runtime-config/spec.md, .spec/features/ai-organization-runtime-config/tasks.md
- Notas: Criar a feature ONP sem paralelizar ordem nem criar feature paralela.

## T-070 — Criar repositorios, credenciais e migration multi-tenant [concluida]
- Refs: US-101, US-102, US-103, AC-421, AC-422, AC-423, AC-424, AC-427, AC-428, AC-429, AC-433, AC-435
- Arquivos: src/ai_agent_runtime/organization_config.py, src/ai_agent_runtime/organization_seed.py, supabase/migrations/202609070001_ai_organization_runtime_config.sql, .spec/features/ai-organization-runtime-config/openai-projects.md
- Notas: Incluir Supabase/Postgres como implementacao inicial atras de abstracoes, sem salvar secrets em claro.

## T-071 — Integrar runtime Z-API/OpenAI com config e credenciais por organizacao [pendente]

- Refs: US-101, US-102, US-104, US-105, AC-421, AC-423, AC-425, AC-426, AC-430, AC-431, AC-432, AC-433, AC-434
- Arquivos: src/ai_agent_runtime/integrations/openai_provider.py, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/whatsapp/zapi.py
- Notas: Preservar fallback legado e logs seguros; nao alterar playbook, RAG, grounding, batching, audio, Calendar ou CRM.

## T-072 — Cobrir isolamento, uso, fallback e compatibilidade com testes [concluida]
- Refs: AC-421, AC-422, AC-423, AC-424, AC-425, AC-426, AC-427, AC-428, AC-429, AC-430, AC-431, AC-432, AC-433, AC-434, AC-435
- Arquivos: test/ai-organization-runtime-config/organization-runtime-config.test.js, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Usar anotacoes `@spec:AC-xxx`, rodar suite, verify e audit --ci.
