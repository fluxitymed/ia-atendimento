# Tasks: AI WhatsApp Z-API Provider

> feature: ai-whatsapp-zapi-provider

## T-042 — Especificar provider Z-API [concluida]

- Refs: US-056, US-057, US-058, US-059, US-060, US-061, AC-177, AC-178, AC-179, AC-180, AC-181, AC-182, AC-183, AC-184, AC-185, AC-186, AC-187, AC-188, AC-189, AC-190, AC-191, AC-192, AC-193, AC-194, AC-195, AC-196, AC-197
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md
- Notas: Registrar Z-API como provider sandbox/MVP, nao definitivo de producao, com contratos oficiais consultados.

## T-043 — Implementar provider e factory Z-API [concluida]

- Refs: US-056, US-057, AC-177, AC-178, AC-179, AC-180, AC-181, AC-182, AC-196, AC-197
- Arquivos: src/ai_agent_runtime/whatsapp/zapi.py, src/ai_agent_runtime/whatsapp/providers.py, src/ai_agent_runtime/whatsapp/__init__.py, .env.example, test/ai-whatsapp-zapi-provider/zapi-provider.test.js
- Notas: Provider concreto deve implementar `WhatsAppProvider` sem expor detalhes da Z-API ao runtime; Meta e Evolution devem continuar selecionaveis.

## T-044 — Implementar webhook Z-API [concluida]

- Refs: US-058, US-059, AC-183, AC-184, AC-185, AC-186, AC-187, AC-188, AC-189, AC-190
- Arquivos: src/ai_agent_runtime/whatsapp/zapi_webhook.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-webhook.test.js
- Notas: Endpoint `POST /webhooks/zapi/whatsapp`, normalizacao de texto/audio/imagem/documento, secret, unknown instance, cross-org, duplicate, ordering e self-message.

## T-045 — Criar runner sandbox Z-API [concluida]

- Refs: US-060, AC-191, AC-192, AC-193, AC-194, AC-195
- Arquivos: src/ai_agent_runtime/whatsapp/zapi_sandbox.py, .spec/features/ai-whatsapp-zapi-provider/zapi-sandbox.md, test/ai-whatsapp-zapi-provider/zapi-sandbox.test.js
- Notas: Smoke offline nao depende da Z-API; chamadas reais devem ser opt-in e nunca marcar `LIVE_VERIFIED` sem execucao real.

## T-046 — Verificar feature e regressao WhatsApp [concluida]

- Refs: US-061, AC-196, AC-197
- Arquivos: test/ai-whatsapp-channel, test/ai-whatsapp-evolution-provider, test/ai-whatsapp-zapi-provider
- Notas: Rodar testes, `onp-spec verify ai-whatsapp-zapi-provider` e `onp-spec audit --ci` sem alterar constituicao global.

## T-047 — Corrigir contrato de seguranca inbound Z-API [concluida]

- Refs: US-058, US-060, AC-183, AC-185, AC-194, AC-195
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, .spec/features/ai-whatsapp-zapi-provider/zapi-sandbox.md, src/ai_agent_runtime/whatsapp/zapi.py, src/ai_agent_runtime/whatsapp/zapi_webhook.py, src/ai_agent_runtime/whatsapp/zapi_sandbox.py, .env.example, test/ai-whatsapp-zapi-provider/zapi-webhook.test.js, test/ai-whatsapp-zapi-provider/zapi-sandbox.test.js
- Notas: Z-API nao documenta secret/signature/header custom para callbacks recebidos; remover `ZAPI_WEBHOOK_SECRET` como requisito obrigatorio de inbound e preservar seguranca por HTTPS, instancia conhecida e isolamento por organizacao.

## T-048 — Corrigir resposta generica no caminho live Z-API [concluida]

- Refs: US-062, AC-198, AC-199, AC-200, AC-201, AC-202
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/state.py, src/ai_agent_runtime/graph.py, src/ai_agent_runtime/whatsapp/adapter.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: A frase generica vinha do ACK default do adapter quando o runtime nao produzia texto. O caminho live deve enviar a resposta gerada pelo runtime e falhas nao podem ser mascaradas como sucesso.

## T-049 — Diagnosticar e corrigir HTTP 400 no runtime live Z-API [concluida]

- Refs: US-063, AC-203, AC-204, AC-205, AC-206, AC-207
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Separar falhas HTTP por provider/estagio, preservar logs seguros e corrigir incompatibilidade entre organizationId logico Z-API e coluna UUID do Supabase sandbox. Causa live comprovada: Supabase PostgREST retornava `22P02` para filtro com slug logico; o servidor agora usa o UUID deterministico persistido pelo sandbox.

## T-050 — Remover dependencia acidental de LangSmith no servidor Z-API [concluida]

- Refs: US-064, AC-208, AC-209
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/sandbox_ids.py, src/ai_agent_runtime/sandbox/dataset.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: IDs logicos e UUID deterministico de sandbox foram movidos para modulo neutro sem side effects. O servidor live Z-API nao importa mais `ai_agent_runtime.sandbox` para acessar constantes.

## T-051 — Corrigir segundo turno e grounding live Z-API [concluida]

- Refs: US-065, AC-210, AC-211, AC-212, AC-213, AC-214, AC-215
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/graph.py, src/ai_agent_runtime/whatsapp/adapter.py, src/ai_agent_runtime/whatsapp/channel.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js, test/ai-whatsapp-channel/whatsapp-channel.test.js
- Notas: Garantir exatamente-uma-vez logico no happy path, visibilidade de descartes, historico no segundo turno e bloqueio de claims factuais sem evidencia. A dupla execucao aparente vinha da reemissao dos eventos do graph pelo adapter; o segundo turno sem `webhook_received` indica callback nao entregue ao processo local, nao descarte interno.

## T-052 — Corrigir retrieval Botox e persistencia de historico live Z-API [concluida]

- Refs: US-066, AC-216, AC-217, AC-218, AC-219, AC-220, AC-221, AC-222
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/whatsapp/channel.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Busca live deixou de fazer `ILIKE` da frase inteira e passou a consultar termos lexicais relevantes contra versoes publicadas/processadas; historico local do sandbox live passou a persistir em JSON ignorado pelo Git, sem alterar grounding, Calendar, Meta, Evolution ou CRM.

## T-053 — Ajustar comportamento comercial e handoff silencioso live [concluida]

- Refs: US-067, AC-228, AC-229, AC-230, AC-223, AC-224, AC-225, AC-226, AC-227
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Diferenciar pergunta factual sem suporte, conducao comercial conversacional e negativa `CLOSED_WORLD`, sem hardcodear respostas por frase e sem enviar outbound em handoff.

## T-054 — Corrigir desambiguacao contextual de respostas curtas [concluida]

- Refs: US-070, AC-235, AC-236, AC-237, AC-238, AC-239
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/whatsapp/channel.py, src/ai_agent_runtime/whatsapp/adapter.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Usar a pergunta anterior da IA e a relacao do turno antes de classificar `UNSUPPORTED_ATTRIBUTE`, preservando a pergunta factual real sobre marca/fabricante.

## T-055 — Separar falha factual do usuario e alucinacao do modelo [concluida]
- Refs: US-072, AC-242, AC-243, AC-244, AC-245, AC-246, AC-247, AC-248
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Manter grounding forte; quando `user_requires_evidence=false` e o modelo introduz claim factual sem suporte, rejeitar a resposta e fazer no maximo um retry `CONVERSATIONAL_NO_FACTS`, sem handoff falso.

## T-056 — Migrar sandbox Z-API para Dr. Leonardo Carvalho [concluida]
- Refs: US-083, AC-204, AC-216, AC-217, AC-280, AC-281, AC-282, AC-283, AC-284, AC-285
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, .spec/features/ai-whatsapp-zapi-provider/zapi-sandbox.md, src/ai_agent_runtime/sandbox_ids.py, src/ai_agent_runtime/sandbox/dataset.py, src/ai_agent_runtime/sandbox/supabase_smoke.py, src/ai_agent_runtime/sandbox/google_calendar_smoke.py, src/ai_agent_runtime/sandbox/langsmith_smoke.py, src/ai_agent_runtime/sandbox/scenarios.py, src/ai_agent_runtime/whatsapp/zapi.py, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/commercial/playbook.py, src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/dataset.py, src/ai_agent_runtime/evaluation/metrics.py, src/ai_agent_runtime/evaluation/runner.py, .env.example, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js, test/ai-whatsapp-zapi-provider/zapi-provider.test.js, test/ai-agent-live-sandbox/live-sandbox.test.js, test/ai-agent-evaluation/evaluation.test.js
- Notas: Organizacao ativa do sandbox Z-API passa a ser `sandbox-org-dr-leonardo-carvalho` com UUID deterministico preservado, catalogo `OPEN_WORLD`, handoff clinico silencioso e avaliacoes comerciais reais sem dados reais de paciente.

## T-057 — Corrigir paridade Supabase live e grounding de configuracao [concluida]
- Refs: US-085, AC-291, AC-292, AC-293
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Diagnostico live confirmou ausencia de organizacao/documentos/chunks/embeddings do Dr. Leonardo no Supabase antes do seed; dataset foi persistido pelo smoke oficial e o grounding passou a reconhecer somente identidade/local/horario de configuracao autorizada, sem liberar fatos de procedimento sem RAG.

## T-058 — Corrigir contexto comercial, retrieval contextual e naturalidade live [concluida]
- Refs: US-086, AC-294, AC-295, AC-296, AC-297, AC-298, AC-299, AC-300
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/commercial/playbook.py, src/ai_agent_runtime/whatsapp/adapter.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Respostas curtas como `Os dois` agora sao resolvidas pelo contexto comercial acumulado; o retrieval usa query contextual, evidencia recente do mesmo conversationId/organizationId pode ser reaproveitada com escopo auditavel, e o prompt reforca anti-eco, anti-formulario e grounding forte.

## T-059 — Implementar batching/debounce por conversationId [concluida]
- Refs: US-088, AC-310, AC-311, AC-312, AC-313, AC-314, AC-315, AC-316, AC-317
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, .env.example, src/ai_agent_runtime/whatsapp/batching.py, src/ai_agent_runtime/whatsapp/channel.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-batching.test.js
- Notas: Agrupar inbound text consecutivo por organizacao/provider/conversa, defaults `MESSAGE_BATCH_DEBOUNCE_MS=6000` e `MESSAGE_BATCH_MAX_WAIT_MS=12000`, lock por conversa, early flush deterministico e logs de observabilidade sem alterar grounding/RAG/Calendar.

## T-060 — Aplicar lacuna comercial e memoria operacional no caminho Z-API [concluida]
- Refs: US-091, AC-330, AC-331, AC-332
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/whatsapp/adapter.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Grounding live bloqueia exposicao de lacuna interna, regenera resposta comercial segura quando aplicavel e passa o telefone do canal para o estado operacional.

## T-061 — Publicar briefing v2 do Dr. Leonardo com avaliacao gratuita [concluida]
- Refs: US-092, AC-344, AC-345, AC-346, AC-347, AC-348, AC-349, AC-350
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/sandbox_ids.py, src/ai_agent_runtime/sandbox/dataset.py, src/ai_agent_runtime/sandbox/supabase_smoke.py, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/evaluation/dataset.py, test/ai-agent-live-sandbox/live-sandbox.test.js, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js, test/ai-agent-evaluation/evaluation.test.js
- Notas: Fonte intermediaria substituiu a versao anterior; v1 fica `SUPERSEDED`, v2 fica `PUBLISHED`, avaliacao gratuita para busca por procedimento passa a ser fato autorizado e a ambiguidade antiga e rejeitada.

## T-062 — Corrigir resiliencia de retrieval e segundo turno operacional live [concluida]
- Refs: US-093, AC-351, AC-352, AC-353, AC-354, AC-355, AC-356, AC-357, AC-358, AC-359
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/whatsapp/batching.py, src/ai_agent_runtime/commercial/playbook.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js, test/ai-whatsapp-zapi-provider/zapi-batching.test.js
- Notas: Evitar que connection reset transitorio do Supabase silencie turno operacional, aplicar retry limitado em retrieval factual, decidir necessidade de RAG antes da busca e impedir que texto da assistente crie medo/objecao no estado do paciente.

## T-063 — Corrigir memoria operacional, fatos respondidos e cadastro live [concluida]
- Refs: US-094, AC-360, AC-361, AC-362, AC-363, AC-364, AC-365, AC-366, AC-367, AC-368, AC-369, AC-370, AC-371
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/commercial/playbook.py, src/ai_agent_runtime/graph.py, src/ai_agent_runtime/whatsapp/adapter.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-commercial-agent-playbook/commercial-playbook.test.js, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Separar apresentacao explicita, memoria factual respondida e memoria cadastral estruturada; turnos operacionais de cadastro/agendamento nao devem chamar RAG nem regressar para discovery.

## T-064 — Corrigir identidade canonica e idempotencia global Z-API [concluida]
- Refs: US-096, AC-373, AC-374, AC-375, AC-376, AC-377, AC-378, AC-379, AC-380
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/whatsapp/zapi_webhook.py, src/ai_agent_runtime/whatsapp/channel.py, src/ai_agent_runtime/whatsapp/adapter.py, src/ai_agent_runtime/whatsapp/batching.py, test/ai-whatsapp-zapi-provider/zapi-batching.test.js, test/ai-whatsapp-zapi-provider/zapi-webhook.test.js
- Notas: Deduplicar `(providerAccountId, providerMessageId)` antes de resolver conversa/lote/runtime e resolver aliases phone/LID de forma persistente e escopada ao provider account.

## T-065 — Implementar audio inbound live Z-API com STT e batching multimodal [concluida]
- Refs: US-097, AC-381, AC-382, AC-383, AC-384, AC-385, AC-386, AC-387, AC-388, AC-389, AC-390
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, .env.example, src/ai_agent_runtime/integrations/config.py, src/ai_agent_runtime/whatsapp/media.py, src/ai_agent_runtime/whatsapp/__init__.py, src/ai_agent_runtime/whatsapp/zapi.py, src/ai_agent_runtime/whatsapp/zapi_webhook.py, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/whatsapp/batching.py, src/ai_agent_runtime/whatsapp/adapter.py, test/ai-runtime-integrations/integrations.test.js, test/ai-whatsapp-zapi-provider/zapi-batching.test.js, test/ai-whatsapp-zapi-provider/zapi-webhook.test.js, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js, test/ai-agent-evaluation/evaluation.test.js
- Notas: Audio recebido deve ser baixado/transcrito por provider STT separado, participar do batching como conteudo operacional com proveniencia, manter outbound texto-only e preservar idempotencia/canonical identity.

## T-066 — Priorizar intencao do turno atual sobre memoria comercial [concluida]
- Refs: US-098, AC-391, AC-392, AC-393, AC-394, AC-395, AC-396, AC-397, AC-398, AC-399, AC-400
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/commercial/playbook.py, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/dataset.py, src/ai_agent_runtime/evaluation/metrics.py, test/ai-commercial-agent-playbook/commercial-playbook.test.js, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js, test/ai-agent-evaluation/evaluation.test.js
- Notas: Separar memoria persistente, contexto ativo e intencao do turno atual; permitir `RESPOND_ONLY`, `WAIT_FOR_PATIENT` e continuidade semantica sem forcar CTA em saudacoes, perguntas laterais ou retomadas neutras.

## T-067 — Corrigir retomada neutra OTHER e ingress de midia Z-API [concluida]
- Refs: US-099, AC-401, AC-402, AC-403, AC-404, AC-405, AC-406, AC-407, AC-408, AC-409, AC-410
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/commercial/playbook.py, src/ai_agent_runtime/whatsapp/zapi_server.py, src/ai_agent_runtime/whatsapp/zapi_webhook.py, test/ai-commercial-agent-playbook/commercial-playbook.test.js, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js, test/ai-whatsapp-zapi-provider/zapi-webhook.test.js
- Notas: `OTHER` neutro com contexto stale deve short-circuitar antes de discovery/retrieval/model; ingress do webhook Z-API deve registrar texto, imagem e audio no primeiro ponto seguro antes de normalizacao, com rejeicoes explicitas.

## T-068 — Preparar servidor Z-API para Render Web Service 24/7 [concluida]
- Refs: US-100, AC-411, AC-412, AC-413, AC-414, AC-415, AC-416, AC-417, AC-418, AC-419, AC-420
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, .spec/features/ai-whatsapp-zapi-provider/render-web-service.md, .env.example, src/ai_agent_runtime/whatsapp/channel.py, src/ai_agent_runtime/whatsapp/adapter.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js, test/ai-whatsapp-zapi-provider/zapi-webhook.test.js
- Notas: Binda em `0.0.0.0`, usa `PORT`, expoe `/health`, configura store persistente em `/var/data`, adiciona `AI_INBOUND_ENABLED` e preserva idempotencia/seguranca sem alterar playbook, RAG, grounding, Calendar, CRM, Meta ou Evolution.

## T-073 — Publicar briefing v3 authoritative do Dr. Leonardo [concluida]

- Refs: US-092, US-106, AC-344, AC-345, AC-346, AC-347, AC-348, AC-349, AC-350, AC-436, AC-437, AC-438, AC-439, AC-440, AC-441, AC-442, AC-443, AC-444, AC-445
- Arquivos: .spec/features/ai-whatsapp-zapi-provider/spec.md, .spec/features/ai-whatsapp-zapi-provider/tasks.md, src/ai_agent_runtime/sandbox_ids.py, src/ai_agent_runtime/sandbox/dataset.py, src/ai_agent_runtime/sandbox/supabase_smoke.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-agent-live-sandbox/live-sandbox.test.js, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Nova fonte `Briefing_Assistente_Comercial_Dr_Leonardo_Carvalho.pdf` substitui a fonte anterior; v3 fica current/PUBLISHED, v1/v2 ficam SUPERSEDED, sala Pituba passa a 4022 e regras Carvalho de agenda/handoff ficam escopadas. Publicacao live via pipeline Supabase/OpenAI embeddings retornou `LIVE_VERIFIED`, com 5 document_versions v3 current/PUBLISHED, 10 versoes antigas superseded/non-current, 5 chunks current da Carvalho e isolamento cross-org validado.
