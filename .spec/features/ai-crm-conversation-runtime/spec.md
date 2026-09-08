# Spec: AI CRM Conversation Runtime

> feature: ai-crm-conversation-runtime
> status: em-implementacao

## Contexto

Integrar o runtime real da IA/Z-API ao cockpit operacional do CRM, persistindo conversas, mensagens e eventos no Supabase do CRM e consultando o modo atual da conversa antes de qualquer resposta automatica.

O Supabase da IA/RAG e o Supabase do CRM sao dominios distintos. A integracao usa credenciais backend exclusivas do CRM e um mapeamento explicito entre a instancia Z-API e o UUID da organizacao no CRM.

## Historias

### US-108 — Persistencia operacional no CRM

Como operador do CRM, quero que mensagens do runtime aparecam no Atendimento IA, para acompanhar a conversa real sem depender do store local.

#### AC-457 — Inbound cria ou localiza conversa escopada

- **Dado** um inbound de uma instancia vinculada a uma organizacao do CRM
- **Quando** o webhook e processado
- **Entao** a conversa e criada ou localizada por `organization_id`, `channel=whatsapp` e `external_conversation_id` escopado por instancia Z-API mais contato canonico, sem mistura entre organizacoes ou instancias da mesma organizacao; uma nova conversa persiste o `phone_number` WhatsApp canonico em campo separado quando ele estiver disponivel, mantendo `null` para identidade somente LID

#### AC-458 — Inbound persiste mensagem do cliente

- **Dado** uma conversa operacional resolvida
- **Quando** uma mensagem inbound valida chega
- **Entao** `ai_messages` recebe a mensagem como `inbound/customer` e a conversa atualiza `last_message_at`, `last_customer_message_at` e `updated_at`

#### AC-459 — Inbound duplicado e idempotente

- **Dado** o mesmo `external_message_id` recebido mais de uma vez
- **Quando** os webhooks sao processados
- **Entao** cada ID fisico do provider em um lote e inserido/idempotency-checkado individualmente com seu conteudo, tipo e horario; somente IDs novos recebem `MESSAGE_RECEIVED`, um lote so de duplicatas nao executa automacao e um lote misto executa no maximo um turno logico

#### AC-460 — Evento de recebimento e auditavel

- **Dado** uma mensagem inbound nova persistida
- **Quando** o processamento operacional comeca
- **Entao** um evento `MESSAGE_RECEIVED` e registrado na mesma organizacao e conversa

### US-109 — Gate operacional controlado pelo CRM

Como operador, quero que o modo atual no CRM governe a automacao, para assumir uma conversa sem reiniciar o runtime.

#### AC-461 — Modo IA permite processamento

- **Dado** uma conversa cujo modo atual no CRM e `ai`
- **Quando** chega uma nova mensagem
- **Entao** o runtime pode chamar a LLM e preparar uma resposta automatica

#### AC-462 — Modo humano bloqueia LLM e outbound

- **Dado** uma conversa cujo modo atual no CRM e `human`
- **Quando** chega uma nova mensagem
- **Entao** a mensagem permanece persistida, mas a LLM e o envio outbound nao sao chamados

#### AC-463 — Takeover e respeitado sem restart

- **Dado** uma conversa processada anteriormente em modo `ai`
- **Quando** o CRM altera o modo para `human` antes da proxima mensagem
- **Entao** a proxima mensagem consulta novamente o CRM e bloqueia a automacao

#### AC-464 — Falha de consulta usa fail closed

- **Dado** indisponibilidade ou erro ao confirmar o modo no CRM
- **Quando** uma mensagem inbound e recebida
- **Entao** o webhook conclui sem loop, nao chama a LLM e nao envia resposta automatica

#### AC-465 — Store local nao sobrescreve decisao do CRM

- **Dado** um estado local divergente do modo persistido no CRM
- **Quando** o gate operacional e avaliado
- **Entao** prevalece sempre o modo lido no CRM

### US-110 — Lifecycle auditavel da resposta da IA

Como operador, quero acompanhar geracao e entrega da resposta, para diagnosticar falhas sem expor segredos.

#### AC-466 — Inicio da resposta e registrado

- **Dado** uma conversa confirmada em modo `ai`
- **Quando** o runtime inicia a geracao
- **Entao** um evento `AI_RESPONSE_STARTED` e persistido antes da chamada da LLM

#### AC-467 — Resposta e persistida antes do envio externo

- **Dado** uma resposta gerada pela IA
- **Quando** ela sera enviada pela Z-API
- **Entao** uma mensagem `outbound/ai` e criada com estado `pending_external_delivery` antes da chamada externa

#### AC-468 — Entrega concluida atualiza mensagem e conversa

- **Dado** uma resposta persistida e aceita pela Z-API
- **Quando** o envio termina
- **Entao** a mensagem recebe estado `sent`, o identificador externo e o horario, a conversa atualiza `last_message_at` e `last_ai_message_at`, e `AI_RESPONSE_COMPLETED` e registrado

#### AC-469 — Falha de envio fica registrada e sanitizada

- **Dado** uma falha no envio da resposta pela Z-API
- **Quando** o erro e tratado
- **Entao** a mensagem recebe estado `failed` e um evento `AI_RESPONSE_FAILED` de severidade `error` guarda exatamente `error_code`, `error_type`, `safe_message`, `attempt` e `provider`, sem credenciais, URLs ou erro bruto

### US-111 — Handoff persistente e seguro

Como operador, quero que handoffs obrigatorios interrompam a automacao, para evitar respostas inadequadas enquanto um humano assume.

#### AC-470 — Handoff obrigatorio persiste estado

- **Dado** uma decisao `HUMAN_HANDOFF_REQUIRED`
- **Quando** o runtime conclui o turno
- **Entao** a conversa recebe `handoff_requested=true`, motivo real, origem `ai`, horario, status `HANDOFF_REQUESTED` e modo `human`

#### AC-471 — Handoff bloqueia mensagens posteriores

- **Dado** uma conversa movida automaticamente para modo `human` por handoff
- **Quando** chegam mensagens futuras
- **Entao** elas sao persistidas, mas nao geram LLM nem outbound ate o CRM devolver o modo para `ai`

#### AC-472 — Runtime nao duplica eventos de takeover do CRM

- **Dado** que o operador usa os controles de takeover no CRM
- **Quando** o runtime observa a mudanca de modo
- **Entao** ele nao cria eventos `HUMAN_TAKEOVER` ou `AI_TAKEOVER`

### US-112 — Configuracao multiempresa e resiliencia

Como mantenedor, quero separar os dominios e credenciais, para operar o cliente correto sem vazamento entre organizacoes.

#### AC-473 — Mapping de instancia para organizacao CRM e deterministico

- **Dado** uma configuracao explicita de instancias Z-API
- **Quando** uma mensagem e recebida
- **Entao** o UUID CRM e resolvido exclusivamente por `instanceId`, sem inferencia por telefone ou por dados do payload

#### AC-474 — Supabase CRM usa credencial backend separada

- **Dado** a integracao habilitada
- **Quando** o cliente CRM e construido
- **Entao** ele usa `CRM_SUPABASE_URL` e `CRM_SUPABASE_SERVICE_ROLE_KEY` somente no backend, sem reutilizar anon key ou credenciais da IA/RAG

#### AC-475 — Erros nunca vazam segredos

- **Dado** um erro contendo tokens, Authorization, JWT, URLs de banco ou chaves
- **Quando** logs ou eventos seguros sao produzidos
- **Entao** nenhum segredo aparece no texto ou metadata persistida

#### AC-476 — Integracao preserva Z-API e base de conhecimento

- **Dado** a integracao CRM habilitada ou desabilitada em testes existentes
- **Quando** as suites Z-API, runtime, RAG e KB rodam
- **Entao** os contratos existentes continuam passando sem alteracao de UI, endpoints CRM, schema, RLS ou migrations

## Decisoes de projeto

- O Supabase CRM e a fonte da verdade para `mode` e handoff; o JSON local preserva apenas contexto e idempotencia auxiliar.
- Handoff obrigatorio altera automaticamente `mode=human` e suprime o outbound do turno.
- A integracao usa REST/PostgREST server-side com service role exclusiva do CRM.
- `contact_id` permanece `null` neste lote; nao ha inferencia global por telefone.
- O outbound e criado como `pending_external_delivery` antes da Z-API e atualizado para `sent` ou `failed` depois.
- A identidade externa da conversa e `zapi:<instanceId-percent-encoded>:<canonicalContact-percent-encoded>`; ela separa instancias da mesma organizacao sem depender do telefone. `phone_number` e persistido separadamente, apenas na criacao e quando disponivel; em eventos somente LID permanece `null` e nunca altera `mode`, `status` ou handoff existentes.
- O webhook duplicado e suprimido pela unicidade real de cada `external_message_id` no CRM, inclusive apos restart; IDs compostos de lote nunca sao persistidos.
- Com `CRM_AI_MONITORING_ENABLED=true`, qualquer falha em persistir inbound ou confirmar o modo usa fail closed e retorna processamento aceito sem executar IA.

## Fora de escopo

- Alterar UI ou endpoints do CRM.
- Alterar schema, migrations ou RLS.
- Aplicar alteracoes manualmente no banco.
- Criar WebSocket, analytics ou resolucao automatica de `contact_id`.
- Persistir `HUMAN_TAKEOVER` ou `AI_TAKEOVER` pelo runtime.

## Suposicoes

| ID | Suposicao | Status | Resolucao |
|---|---|---|---|
| ASM-043 | As tabelas e indices de `ai_conversations`, `ai_messages` e `ai_events` descritos no contrato ja existem em Production. | confirmada | Informado pelo usuario. |
| ASM-044 | Handoff obrigatorio deve alterar automaticamente o modo para `human`. | confirmada | Preferencia operacional explicitamente autorizada no pedido. |
| ASM-045 | O UUID CRM de Carvalho/Tavares sera fornecido no ambiente de deploy, sem hardcode no repositorio. | confirmada | O mapping deterministico deve ser configurado com o UUID real do workspace CRM. |
| ASM-046 | `contact_id` pode permanecer nulo neste lote. | confirmada | O pedido autoriza deixar o vinculo nulo quando nao houver resolucao segura. |

## Perguntas em aberto

Nenhuma.
