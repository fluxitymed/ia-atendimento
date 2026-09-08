# Design: AI CRM Conversation Runtime

## Componentes

- `CrmConversationMonitor`: orquestra o lifecycle operacional sem conhecer detalhes da Z-API.
- `CrmConversationRepository`: opera `ai_conversations`, `ai_messages` e `ai_events` via transporte PostgREST injetavel.
- `CrmOrganizationResolver`: resolve `instanceId` para UUID CRM por configuracao explicita.
- `WhatsAppChannelAdapter`: chama o monitor nos limites inbound, gate, geracao, handoff e envio.
- `JsonFileWhatsAppStore`: continua guardando contexto conversacional, mas nao decide o modo oficial.

## Sequencia inbound

1. Normalizar evento e resolver a organizacao da IA/RAG pelo mapping existente.
2. Resolver separadamente o UUID CRM pelo `instanceId`.
3. Upsert da conversa por organizacao CRM, canal e identidade externa `zapi:<instanceId-percent-encoded>:<canonicalContact-percent-encoded>`; o telefone WhatsApp canonico vai em `phone_number` separado somente na criacao, ou permanece `null` quando o provider entrega apenas LID.
4. Para um lote, inserir inbound por cada `external_message_id` constituinte (conteudo/tipo/horario alinhados); conflito de todos encerra o turno, enquanto ao menos uma insercao nova libera um unico turno logico.
5. Registrar `MESSAGE_RECEIVED` somente para cada constituinte novo.
6. Ler novamente a conversa e exigir `mode=ai` antes da LLM.
7. Em erro ou `mode=human`, retornar registro aceito com outbound suprimido.

## Sequencia outbound

1. Registrar `AI_RESPONSE_STARTED` antes da geracao.
2. Se houver handoff, persistir `mode=human`, estado e evento, sem outbound.
3. Para resposta automatica, criar mensagem `pending_external_delivery` antes da Z-API.
4. Em sucesso, atualizar para `sent`, timestamps da conversa e registrar `AI_RESPONSE_COMPLETED`.
5. Em falha, atualizar para `failed` e registrar `AI_RESPONSE_FAILED` com metadata sanitizada.

## Fail-safe

Com a integracao habilitada, falha de persistencia ou leitura do modo cria um resultado local `CRM_MONITORING_BLOCKED`, sem LLM/outbound. O handler continua respondendo HTTP de sucesso para evitar retry infinito do provider.

Midia monitorada nao passa pela materializacao do batching: ela entra primeiro no adapter monitorado, que persiste e confirma o contexto CRM antes de qualquer retry outbound ou handoff.
