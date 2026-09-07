# Tasks: AI WhatsApp Channel

> feature: ai-whatsapp-channel

## T-001 — Especificar canal WhatsApp desacoplado [concluida]
- Refs: US-038, US-039, US-040, US-041, US-042, US-043, US-044, US-045, US-046, AC-124, AC-125, AC-126, AC-127, AC-128, AC-129, AC-130, AC-131, AC-132, AC-133, AC-134, AC-135, AC-136, AC-137, AC-138, AC-139, AC-140, AC-141, AC-142, AC-143, AC-144
- Arquivos: .spec/features/ai-whatsapp-channel/spec.md, .spec/features/ai-whatsapp-channel/tasks.md
- Notas: Fornecedor real fica bloqueado por Q-006; implementacao offline pode avancar.

## T-002 — Implementar contrato, mensagens normalizadas e store do canal [concluida]
- Refs: AC-124, AC-126, AC-127, AC-129, AC-130, AC-141, AC-142
- Arquivos: src/ai_agent_runtime/whatsapp/channel.py, src/ai_agent_runtime/whatsapp/__init__.py, test/ai-whatsapp-channel/whatsapp-channel.test.js
- Notas: In-memory store e provider fake para idempotencia, ordering e conversation mapping.

## T-003 — Implementar adapter texto-runtime e handoff seguro [concluida]
- Refs: AC-125, AC-128, AC-139, AC-140
- Arquivos: src/ai_agent_runtime/whatsapp/adapter.py, test/ai-whatsapp-channel/whatsapp-channel.test.js
- Notas: Adapter chama `AgentRuntimeGraph`; nao decide fatos/agenda/grounding.

## T-004 — Implementar processamento multimodal offline [concluida]
- Refs: AC-131, AC-132, AC-133, AC-134, AC-135, AC-136, AC-137, AC-138
- Arquivos: src/ai_agent_runtime/whatsapp/media.py, test/ai-whatsapp-channel/whatsapp-channel.test.js
- Notas: STT fake injetavel, validacao de arquivo, politica segura para imagem/documento.

## T-005 — Ampliar avaliacao multimodal offline [concluida]
- Refs: AC-143, AC-144
- Arquivos: src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/dataset.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Adicionar cenarios multimodais mantendo metricas criticas em zero.

## T-006 — Validar ONP e registrar bloqueio do provider real [concluida]
- Refs: AC-124, AC-144
- Arquivos: .spec/features/ai-whatsapp-channel/tasks.md, .spec/verification/ai-whatsapp-channel.json
- Notas: Rodar testes, verify e audit; parar antes de webhook/provider real ate decisao do fornecedor.

## T-007 — Implementar provider Meta WhatsApp Cloud API [concluida]
- Refs: AC-145, AC-146, AC-147, AC-148
- Arquivos: .env.example, src/ai_agent_runtime/whatsapp/meta.py, src/ai_agent_runtime/whatsapp/__init__.py, test/ai-whatsapp-channel/meta-provider.test.js
- Notas: Provider concreto atras de `WhatsAppProvider`, com transport injetavel e sem hardcode de secrets.

## T-008 — Implementar webhook Meta seguro [concluida]
- Refs: AC-149, AC-150, AC-151, AC-152, AC-153
- Arquivos: src/ai_agent_runtime/whatsapp/meta_webhook.py, src/ai_agent_runtime/whatsapp/webhook_server.py, test/ai-whatsapp-channel/meta-webhook.test.js
- Notas: GET verification, assinatura `X-Hub-Signature-256`, parser seguro e controller fino que delega ao adapter.

## T-009 — Implementar smoke Meta opt-in [concluida]
- Refs: AC-154, AC-155
- Arquivos: src/ai_agent_runtime/whatsapp/meta_sandbox.py, test/ai-whatsapp-channel/meta-sandbox.test.js
- Notas: Suite offline nao depende de Meta; live real fica bloqueado ate credenciais e URL publica.

## T-010 — Validar ONP apos integracao Meta [concluida]
- Refs: AC-145, AC-155
- Arquivos: .spec/features/ai-whatsapp-channel/tasks.md, .spec/verification/ai-whatsapp-channel.json
- Notas: Rodar test suite, verify e audit; parar antes de pacientes reais/CRM/central.

## T-011 — Implementar handoff silencioso no adapter WhatsApp [concluida]
- Refs: AC-226, AC-227, AC-223
- Arquivos: .spec/features/ai-whatsapp-channel/spec.md, .spec/features/ai-whatsapp-channel/tasks.md, src/ai_agent_runtime/whatsapp/channel.py, src/ai_agent_runtime/whatsapp/adapter.py, test/ai-whatsapp-channel/whatsapp-channel.test.js
- Notas: `HUMAN_HANDOFF_REQUIRED` deve registrar contexto e suprimir outbound automatico; conversas em handoff nao podem seguir chamando runtime enquanto nao houver liberacao humana.
