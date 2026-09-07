# AI WhatsApp Channel

> feature: ai-whatsapp-channel
> status: em-implementacao

## Objetivo

Conectar o agente de atendimento ja validado em sandbox ao WhatsApp sem acoplar o canal ao cerebro do agente.

WhatsApp e apenas canal de entrada/saida:

```text
WhatsApp Provider
↓
WhatsApp Channel Adapter
↓
mensagem normalizada
↓
Agent Runtime / LangGraph
↓
RAG / Tools / Grounding / Handoff
↓
resposta autorizada
↓
WhatsApp Channel Adapter
↓
WhatsApp Provider
```

O canal nao pode conter logica paralela de atendimento factual, agenda, grounding, RAG ou handoff que contorne o runtime.

## Regras Herdadas

Esta feature preserva integralmente as regras de:

- `.spec/features/ai-customer-service/spec.md`
- `.spec/features/ai-agent-runtime/spec.md`
- `.spec/features/ai-runtime-integrations/spec.md`
- `.spec/features/ai-agent-evaluation/spec.md`
- `.spec/features/ai-agent-live-sandbox/spec.md`

Regras inegociaveis:

- conhecimento pre-treinado do LLM nao e fonte factual autorizada sobre a clinica;
- informacao factual sem suporte gera `HUMAN_HANDOFF_REQUIRED`;
- resposta ao paciente nao expoe RAG, retrieval, base, documento, score ou falta de evidencia;
- grounding continua obrigatorio antes de resposta factual;
- `SCHEDULING_CONTEXT_ACTIVE` continua obrigatorio antes de agenda;
- cross-organization retrieval, persistencia ou conversation mapping e proibido;
- conteudo de midia/documento recebido e dado, nao instrucao privilegiada;
- imagens/documentos medicos nao autorizam diagnostico, interpretacao clinica ou conduta.

## Escopo Atual

Implementar contrato abstrato de canal, adapter independente de fornecedor, fakes offline, processamento multimodal seguro, provider concreto Meta WhatsApp Cloud API atras de `WhatsAppProvider`, webhook seguro e smoke tests opt-in.

O fornecedor real aprovado para esta etapa e:

```text
Meta WhatsApp Cloud API
```

O runtime continua sem conhecer detalhes da Meta.

## Estados

- `IMPLEMENTED`: contrato, adapters, fakes, processamento offline e testes existem.
- `BLOCKED_MISSING_CREDENTIALS`: provider/webhook/smoke real foi solicitado sem credenciais Meta ou URL publica.
- `LIVE_VERIFIED`: reservado para futuro teste real com numero sandbox/test number aprovado.

## Historias de usuario e criterios de aceite

### US-038 — Canal desacoplado do runtime

Como arquiteto, quero que WhatsApp seja apenas canal, para trocar provider sem alterar o LangGraph nem enfraquecer as regras do agente.

#### AC-124 — Provider abstrato define operacoes do canal

- **Dado** que o canal WhatsApp sera integrado
- **Quando** o codigo do canal e inspecionado
- **Entao** existe um contrato `WhatsAppProvider` com envio de texto, envio de midia, download de midia e marcacao como lida
- **E** o runtime nao depende de fornecedor real de WhatsApp.

#### AC-125 — Adapter nao contem logica paralela de atendimento

- **Dado** um evento WhatsApp recebido
- **Quando** ele e processado pelo canal
- **Entao** o adapter normaliza a mensagem e chama o `AgentRuntimeGraph`
- **E** nao decide resposta factual, agenda ou grounding diretamente.

### US-039 — Mensagem normalizada independente de fornecedor

Como runtime, quero receber uma mensagem interna estavel, para nunca depender de payload bruto do provider.

#### AC-126 — InboundMessage preserva campos obrigatorios

- **Dado** payloads de texto, audio, imagem ou documento
- **Quando** o adapter normaliza o evento
- **Entao** a mensagem interna preserva `id`, `providerMessageId`, `organizationId`, `conversationId`, `contactExternalId`, tipo, texto, referencia de midia, MIME type, nome de arquivo, timestamp e metadados.

#### AC-127 — Conversation mapping e isolado por organizacao

- **Dado** dois contatos externos iguais em organizacoes diferentes
- **Quando** o canal resolve a conversa
- **Entao** os `conversationId` sao diferentes
- **E** nenhum `organizationId` enviado pelo paciente e aceito como fonte de verdade.

### US-040 — Texto entra no runtime com idempotencia e ordem

Como paciente, quero que mensagens de texto sejam processadas uma vez e em ordem, para evitar respostas duplicadas ou contexto incoerente.

#### AC-128 — Texto normalizado entra no runtime

- **Dado** uma mensagem WhatsApp `TEXT`
- **Quando** o adapter processa o evento
- **Entao** ele cria `AgentState` com `organizationId`, `conversationId`, historico e texto atual
- **E** retorna resposta textual autorizada pelo runtime.

#### AC-129 — Webhook duplicado nao reprocessa mensagem

- **Dado** duas entregas com o mesmo `providerMessageId`
- **Quando** o adapter recebe a repeticao
- **Entao** apenas uma execucao do runtime ocorre
- **E** apenas uma resposta outbound e enviada.

#### AC-130 — Mensagens proximas preservam ordem por conversa

- **Dado** mensagens sequenciais na mesma conversa
- **Quando** elas sao recebidas em ordem
- **Entao** o historico operacional preserva essa ordem
- **E** cada execucao enxerga o contexto anterior da conversa.

### US-041 — Audio e transcrito antes do runtime

Como paciente, quero enviar audio e ser compreendido, para continuar o atendimento pelo WhatsApp sem digitar.

#### AC-131 — Audio compreensivel vira texto operacional

- **Dado** uma mensagem `AUDIO` com arquivo valido
- **Quando** o canal baixa, valida e transcreve a midia
- **Entao** a transcricao e enviada ao runtime como texto operacional
- **E** a referencia ao audio original permanece no contexto.

#### AC-132 — Audio ruim solicita nova tentativa sem inventar conteudo

- **Dado** um audio sem transcricao utilizavel
- **Quando** o processamento de midia falha de forma recuperavel
- **Entao** o resultado e `MEDIA_RETRY_REQUIRED`
- **E** a resposta ao paciente pede reenvio naturalmente, sem mencionar STT, modelo ou erro tecnico.

### US-042 — Imagem e documento seguem politica multimodal segura

Como paciente, quero enviar imagens e documentos, para que a equipe/agente recebam materiais sem a IA interpretar clinicamente o que nao pode.

#### AC-133 — Imagem administrativa compreensivel pode seguir para o runtime

- **Dado** uma imagem nao clinica e compreendida com seguranca
- **Quando** a politica de midia avalia o conteudo
- **Entao** o canal produz texto operacional administrativo
- **E** preserva a referencia original da imagem.

#### AC-134 — Imagem ambigua ou clinica exige handoff

- **Dado** uma imagem ambigua, ilegivel ou clinica
- **Quando** a IA nao consegue compreender com seguranca ou a resposta exigiria analise clinica
- **Entao** a decisao do canal e `HUMAN_HANDOFF_REQUIRED`
- **E** nenhuma interpretacao medica e enviada ao paciente.

#### AC-135 — Documento suportado extrai apenas conteudo permitido

- **Dado** um documento suportado e legivel
- **Quando** o canal extrai conteudo
- **Entao** apenas informacao administrativa permitida segue como texto operacional
- **E** o arquivo original permanece referenciado.

#### AC-136 — Documento ilegivel ou medico exige handoff

- **Dado** um documento corrompido, ilegivel, nao suportado ou medico
- **Quando** o canal nao consegue compreensao segura ou exigiria interpretacao clinica
- **Entao** a decisao e `HUMAN_HANDOFF_REQUIRED`
- **E** o contexto de handoff preserva metadados e arquivo original.

### US-043 — Midia nao altera controles superiores

Como responsavel de seguranca, quero que conteudo multimodal seja tratado como dado, para impedir prompt injection via audio, imagem ou documento.

#### AC-137 — Prompt injection multimodal nao altera regras

- **Dado** midia ou documento contendo instrucao como ignorar regras, desativar grounding, trocar organizacao ou liberar agenda
- **Quando** o canal processa o conteudo
- **Entao** essas instrucoes permanecem como dado nao privilegiado
- **E** nao alteram `organizationId`, tools, grounding, handoff ou scheduling.

#### AC-138 — Agenda continua protegida em mensagens multimodais

- **Dado** audio transcrito mencionando dia, horario, consulta ou interesse
- **Quando** `SCHEDULING_CONTEXT_ACTIVE` nao esta ativo
- **Entao** nenhuma chamada de agenda e feita pelo canal
- **E** a guarda do runtime continua sendo a unica autorizacao para provider de agenda.

### US-044 — Handoff multimodal preserva contexto

Como atendente humano futuro, quero receber contexto completo de midia, para assumir a conversa sem pedir tudo novamente.

#### AC-139 — Handoff de midia preserva referencia e motivo

- **Dado** audio, imagem ou documento que exige `HUMAN_HANDOFF_REQUIRED`
- **Quando** o canal monta o handoff
- **Entao** preserva mensagem original, tipo, referencia de midia, MIME type, nome do arquivo, transcricao ou texto extraido quando houver, motivo, `conversationId`, `organizationId` e contexto anterior.

#### AC-140 — Mensagem de transicao e segura para paciente

- **Dado** que o canal precisa transferir para humano
- **Quando** a resposta outbound e preparada
- **Entao** ela usa texto natural configuravel
- **E** nao menciona RAG, grounding, STT, OCR, modelo, documento sem evidencia ou erro tecnico.

### US-045 — Persistencia e metricas de canal

Como operador, quero auditar mensagens WhatsApp de sandbox, para medir fluxo sem armazenar binarios grandes no banco.

#### AC-141 — Store registra inbound, outbound, decisao e midia

- **Dado** que uma mensagem e processada
- **Quando** o canal conclui processamento
- **Entao** registra conversa, mensagem inbound normalizada, tipo, transcricao/texto extraido, referencia de midia, decisao, outbound, handoff, timestamps e metricas basicas.

#### AC-142 — Binarios de midia nao sao armazenados diretamente no store conversacional

- **Dado** uma midia recebida
- **Quando** o canal registra historico
- **Entao** armazena referencia segura e metadados
- **E** nao grava bytes do arquivo no registro conversacional.

### US-046 — Avaliacao multimodal offline

Como auditor do agente, quero regressões multimodais offline, para garantir que audio, imagem e documento preservam os gates criticos.

#### AC-143 — Dataset de avaliacao inclui cenarios multimodais

- **Dado** a suite offline de avaliacao
- **Quando** o dataset inicial e carregado
- **Entao** existem cenarios de audio, imagem, documento, midia ambigua, midia clinica e prompt injection multimodal.

#### AC-144 — Metricas criticas permanecem em zero para multimodal

- **Dado** cenarios multimodais avaliados
- **Quando** o resumo agregado e calculado
- **Entao** resposta factual sem suporte, vazamento cross-org, agenda nao autorizada e disponibilidade inventada permanecem em `0`.

### US-047 — Meta WhatsApp Cloud API como provider concreto

Como operador tecnico, quero usar Meta WhatsApp Cloud API atras do contrato existente, para enviar e receber WhatsApp real sem acoplar o runtime ao fornecedor.

#### AC-145 — Configuracao Meta vem do ambiente

- **Dado** que o provider Meta e construido
- **Quando** a configuracao e carregada
- **Entao** ele usa variaveis `WHATSAPP_PROVIDER`, `META_WHATSAPP_ACCESS_TOKEN`, `META_WHATSAPP_PHONE_NUMBER_ID`, `META_WHATSAPP_BUSINESS_ACCOUNT_ID`, `META_WHATSAPP_VERIFY_TOKEN`, `META_WHATSAPP_APP_SECRET` e `META_WHATSAPP_API_VERSION`
- **E** `.env.example` nao contem valores reais de segredo.

#### AC-146 — Meta provider implementa WhatsAppProvider sem alterar contrato

- **Dado** o contrato abstrato existente `WhatsAppProvider`
- **Quando** `MetaWhatsAppCloudProvider` e inspecionado
- **Entao** ele implementa envio de texto, envio de midia, download de midia e marcacao como lida
- **E** o runtime continua dependendo apenas do contrato abstrato.

#### AC-147 — Outbound text usa endpoint oficial de mensagens

- **Dado** uma resposta textual autorizada pelo runtime
- **Quando** o provider Meta envia a mensagem
- **Entao** ele chama `/{phoneNumberId}/messages` com `messaging_product=whatsapp`, `type=text`, destinatario e corpo
- **E** retorna o id de mensagem da Meta sem expor access token.

#### AC-148 — Download de midia usa media ID e nao persiste URL temporaria

- **Dado** audio, imagem ou documento recebido com media ID Meta
- **Quando** o provider baixa a midia
- **Entao** primeiro resolve a URL via Graph API autenticada
- **E** baixa os bytes com autenticacao
- **E** nao trata a URL temporaria como referencia permanente.

### US-048 — Webhook oficial da Meta

Como operador tecnico, quero um webhook Meta seguro, para receber eventos reais sem manter logica de atendimento no controller.

#### AC-149 — GET de verificacao valida verify token

- **Dado** uma chamada GET de verificacao da Meta
- **Quando** `hub.mode=subscribe` e `hub.verify_token` confere
- **Entao** o webhook retorna `hub.challenge` com status 200
- **E** tokens invalidos retornam 403.

#### AC-150 — POST valida assinatura quando app secret existe

- **Dado** um POST de webhook Meta
- **Quando** `META_WHATSAPP_APP_SECRET` esta configurado
- **Entao** o corpo e validado contra `X-Hub-Signature-256`
- **E** assinatura ausente ou invalida e rejeitada.

#### AC-151 — Parser Meta normaliza text/audio/image/document

- **Dado** payload Meta contendo mensagens `text`, `audio`, `image` ou `document`
- **Quando** o webhook parseia o evento
- **Entao** produz eventos internos com provider account, message ID, contato externo, tipo, texto, media ID, MIME, filename, timestamp e metadados
- **E** payload invalido e rejeitado sem chamar o runtime.

#### AC-152 — Controller apenas valida, normaliza, reconhece e delega

- **Dado** um POST valido da Meta
- **Quando** o controller executa
- **Entao** ele valida, parseia, envia acknowledgement adequado e delega ao channel adapter
- **E** nao implementa regras factuais, agenda, grounding ou handoff diretamente.

#### AC-153 — Duplicacao e self-message continuam protegidos no webhook Meta

- **Dado** webhook duplicado ou status/evento refletido de mensagem enviada pelo proprio provider
- **Quando** o webhook processa o payload
- **Entao** duplicatas nao geram nova resposta
- **E** mensagens do proprio numero/status events nao entram novamente no agente.

### US-049 — Smoke live Meta opt-in

Como operador de homologacao, quero smoke tests Meta opt-in, para validar integracao real sem tornar a suite offline dependente de credenciais.

#### AC-154 — Smoke Meta bloqueia claramente sem credenciais

- **Dado** que o smoke Meta live e solicitado
- **Quando** faltam access token, phone number ID, WABA ID, verify token, app secret ou URL publica
- **Entao** o resultado e `BLOCKED_MISSING_CREDENTIALS`
- **E** lista apenas nomes de variaveis ausentes, nunca seus valores.

#### AC-155 — Smoke Meta planeja cenarios live obrigatorios

- **Dado** a integracao Meta configurada
- **Quando** o smoke live for executado em ambiente sandbox
- **Entao** ele cobre verificacao de webhook, inbound text, outbound text, inbound audio, inbound image, inbound document, duplicacao, self-message, handoff e scheduling
- **E** so pode marcar `LIVE_VERIFIED` depois de chamadas reais ao provider aprovado.

### US-069 — Handoff WhatsApp silencioso

Como operador humano, quero que o canal WhatsApp pare de responder automaticamente quando o runtime exigir humano, para que a pessoa assuma a conversa sem uma promessa automatica intermediaria.

#### AC-226 — Handoff requerido nao chama send_text

- **Dado** que o runtime ou a politica de midia retorna `HUMAN_HANDOFF_REQUIRED`
- **Quando** o adapter do WhatsApp registra o turno
- **Entao** nenhum `send_text` e chamado
- **E** os logs incluem `human_handoff_required`, `handoff_reason` e `outbound_suppressed`.

#### AC-227 — Conversa em handoff bloqueia nova autonomia

- **Dado** uma conversa ja marcada como `HUMAN_HANDOFF_REQUIRED`
- **Quando** chega novo callback do mesmo contato sem liberacao humana
- **Entao** o adapter preserva o novo inbound no contexto
- **E** nao chama runtime nem envia outbound automatico.

## Fora de escopo

- CRM, Central de Atendimento ou UI humana.
- Pacientes reais ou dados reais.
- Templates promocionais, campanhas, marketing ou opt-in comercial.
- Produção antes de sandbox/test number aprovado.
- TTS/outbound audio obrigatorio.
- Diagnostico, interpretacao clinica ou recomendacao medica a partir de midia.

## Suposições

| ID | Suposição | Status | Resolução |
|---|---|---|---|
| ASM-018 | A primeira entrega pode usar fakes e stores in-memory para validar contrato, idempotencia, ordering e multimodal offline sem internet. | confirmada | O pedido exige desenvolver tudo que independe do fornecedor real antes de parar. |
| ASM-019 | Speech-to-text deve usar provider compativel com OpenAI, mas testes offline usam fake injetavel para nao depender de credenciais. | confirmada | A stack OpenAI ja foi aprovada e o prompt permite escolha tecnica reversivel. |
| ASM-020 | Resposta inicial a audio pode ser texto, deixando TTS/outbound audio como extensao futura. | confirmada | O prompt permite resposta textual na primeira versao. |
| ASM-021 | Midias originais sao preservadas por referencia/metadados, nao por bytes no store conversacional. | confirmada | O prompt orienta evitar binarios grandes no banco e preservar handoff futuro. |
| ASM-022 | O webhook local pode ser implementado com HTTP server padrao da biblioteca Python para sandbox, sem introduzir framework web obrigatorio. | confirmada | O pedido exige endpoint local e nao exige framework especifico. |
| ASM-031 | A liberacao humana para devolver uma conversa em handoff para a IA ainda nao tem Central de Atendimento; nesta etapa o bloqueio de autonomia e persistido no store do canal e pode ser limpo por operacao futura. | confirmada | Escopo atual nao inicia CRM UI nem central humana. |

## Perguntas em aberto

| ID | Pergunta | Status | Resposta |
|---|---|---|---|
| Q-006 | Qual fornecedor real de WhatsApp deve ser usado para webhook e envio live: Meta Cloud API, Z-API ou outro? | respondida | Meta WhatsApp Cloud API. |
| Q-007 | Quais credenciais e URL publica serao usadas para live sandbox Meta? | respondida | Nao enviar secrets pelo chat. A implementacao deve parar em `BLOCKED_MISSING_CREDENTIALS` ate existirem `META_WHATSAPP_ACCESS_TOKEN`, `META_WHATSAPP_PHONE_NUMBER_ID`, `META_WHATSAPP_BUSINESS_ACCOUNT_ID`, `META_WHATSAPP_VERIFY_TOKEN`, `META_WHATSAPP_APP_SECRET` e URL publica do webhook. |
