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

## T-007 — Cobrir qualidade comercial e handoff silencioso [concluida]
- Refs: US-068, AC-231, AC-232, AC-233, AC-234
- Arquivos: .spec/features/ai-agent-evaluation/spec.md, .spec/features/ai-agent-evaluation/tasks.md, src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/dataset.py, src/ai_agent_runtime/evaluation/metrics.py, src/ai_agent_runtime/evaluation/runner.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Adicionar cenarios e metricas deterministicas para progresso comercial, continuidade contextual, ausencia de resposta enciclopedica inicial, handoff silencioso e handoff desnecessario.

## T-008 — Cobrir ambiguidade contextual em avaliacao comercial [concluida]
- Refs: US-071, AC-240, AC-241
- Arquivos: .spec/features/ai-agent-evaluation/spec.md, .spec/features/ai-agent-evaluation/tasks.md, src/ai_agent_runtime/evaluation/dataset.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Adicionar casos de marca como brand versus marca visivel na pele e respostas curtas que dependem da pergunta anterior.

## T-009 — Medir regeneracao segura e origem de falha factual [concluida]
- Refs: US-073, AC-249, AC-250, AC-251, AC-252, AC-253
- Arquivos: .spec/features/ai-agent-evaluation/spec.md, .spec/features/ai-agent-evaluation/tasks.md, src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/dataset.py, src/ai_agent_runtime/evaluation/metrics.py, src/ai_agent_runtime/evaluation/runner.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Adicionar cenarios e metricas para separar `USER_REQUESTED_UNSUPPORTED_FACT` de `MODEL_INTRODUCED_UNSUPPORTED_FACT`, incluindo retry seguro bem-sucedido e falha interna sem outbound inseguro.

## T-010 — Avaliar playbook comercial global multiturno [concluida]
- Refs: US-082, AC-273, AC-274, AC-275, AC-276, AC-277, AC-278, AC-279
- Arquivos: .spec/features/ai-agent-evaluation/spec.md, .spec/features/ai-agent-evaluation/tasks.md, src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/dataset.py, src/ai_agent_runtime/evaluation/metrics.py, src/ai_agent_runtime/evaluation/runner.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Medir apresentacao, nao repeticao, eficiencia de descoberta, minimum discovery, perguntas/recap excessivos, fadiga, objecoes, CTA/agendamento e escape de fatos sem suporte.

## T-011 — Adicionar avaliacao comercial do Dr. Leonardo [concluida]
- Refs: US-084, AC-286, AC-287, AC-288, AC-289, AC-290
- Arquivos: .spec/features/ai-agent-evaluation/spec.md, .spec/features/ai-agent-evaluation/tasks.md, src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/dataset.py, src/ai_agent_runtime/evaluation/metrics.py, src/ai_agent_runtime/evaluation/runner.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Cenários offline com fatos autorizados do briefing do Dr. Leonardo medem ponte de valor, relevancia comercial, ausencia de empatia performatica, nome da assistente nao extraido como paciente, avaliacao gratuita autorizada e urgencia com handoff silencioso.

## T-012 — Medir retencao de contexto e naturalidade multi-turno [concluida]
- Refs: US-087, AC-301, AC-302, AC-303, AC-304, AC-305, AC-306, AC-307, AC-308, AC-309
- Arquivos: .spec/features/ai-agent-evaluation/spec.md, .spec/features/ai-agent-evaluation/tasks.md, src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/runner.py, src/ai_agent_runtime/evaluation/metrics.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Metricas deterministicas adicionais cobrem retencao de contexto, ganho de informacao, anti-eco, escolha forcada, resposta curta contextual, reuso de evidencia, timing de ponte de valor, naturalidade e conclusao de resposta.

## T-013 — Medir memoria operacional, lacunas internas e estilo WhatsApp [concluida]
- Refs: US-090, AC-333, AC-334, AC-335, AC-336, AC-337, AC-338, AC-339, AC-340, AC-341, AC-342, AC-343
- Arquivos: .spec/features/ai-agent-evaluation/spec.md, .spec/features/ai-agent-evaluation/tasks.md, src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/dataset.py, src/ai_agent_runtime/evaluation/metrics.py, src/ai_agent_runtime/evaluation/runner.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Adicionar cenarios e metricas para exposicao de limitacao interna, memoria operacional, telefone do WhatsApp, coleta cadastral agrupada, escolha tecnica prematura, booking prematuro, repeticao de correcao, Markdown/travessao e clareza de proxima acao.

## T-014 — Medir regressao de memoria operacional live [concluida]
- Refs: US-095, AC-372
- Arquivos: .spec/features/ai-agent-evaluation/spec.md, .spec/features/ai-agent-evaluation/tasks.md, src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/metrics.py, src/ai_agent_runtime/evaluation/runner.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Cobrir metricas para repeticao factual, avaliacao gratuita repetida, apresentacao, appointment intent prematuro, regressao de scheduling, RAG operacional, acuracia cadastral, confusao CPF/RG/CEP, confirmacao redundante, precisao de campos faltantes, inferencia de endereco e eficiencia de conclusao cadastral.
