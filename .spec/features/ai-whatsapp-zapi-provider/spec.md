# Spec: AI WhatsApp Z-API Provider

> feature: ai-whatsapp-zapi-provider
> status: em-implementacao

## Contexto

Adicionar a Z-API como provider concreto de WhatsApp, atras do contrato `WhatsAppProvider`, para validar em sandbox a qualidade comercial da IA em conversas reais antes de investir na infraestrutura definitiva/oficial.

A Z-API opera uma sessao de WhatsApp Web. Nesta feature ela e uma decisao de sandbox/MVP para validacao comercial, nao a arquitetura definitiva de producao.

Arquitetura esperada:

```text
WhatsAppProvider
├── MetaWhatsAppCloudProvider
├── EvolutionWhatsAppProvider
└── ZApiWhatsAppProvider
```

O provider ativo de sandbox passa a ser:

```text
WHATSAPP_PROVIDER=zapi
```

## Organizacao ativa do sandbox

A organizacao ativa do sandbox Z-API para validacao comercial real e:

```text
Dr. Leonardo Carvalho
Clinica Carvalho e Tavares Odontologia Integrada
ZAPI_ORGANIZATION_ID=sandbox-org-dr-leonardo-carvalho
UUID persistido: dfdcdff0-6d5f-58cc-9a83-2829820b7f8e
```

A fonte primaria autorizada para este primeiro cliente de teste e o briefing:

```text
/Users/FernandoAndrade/Desktop/IA - TESTES/BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf
```

Nesta etapa, o projeto registra fatos confirmados do briefing no dataset sandbox, mas nao inventa informacao alem dele. O catalogo de procedimentos do Dr. Leonardo permanece `OPEN_WORLD` porque a completude fechada ainda nao foi comprovada. A ausencia de um procedimento no briefing nao autoriza responder `NOT_OFFERED`.

Esta nova versao substitui o briefing anterior do Dr. Leonardo. A versao anterior nao pode permanecer `PUBLISHED`/current ao mesmo tempo que a nova versao.

Regra comercial autorizada pela nova fonte:

```text
evaluation_is_free = true
scope = casos de busca por procedimento
```

Para pacientes buscando procedimento, incluindo implante e lentes, a IA pode responder diretamente que a avaliacao e gratuita. O valor dos procedimentos continua sendo informado apos avaliacao. Permanecem autorizadas as formas de pagamento PIX, cartao de credito, cartao de debito e boleto, parcela minima de R$ 500 e ausencia de deposito antecipado.

As regras antigas de ambiguidade sobre gratuidade deixam de ser current para esta organizacao. Respostas como `precisa confirmar`, `pode nao ser cobrada`, `depende do caso` ou `a clinica confirma antes` nao podem ser usadas quando a evidencia current e a nova versao do briefing.

O playbook comercial continua global e reutilizavel. Dados como nome da clinica, profissional, horarios e unidades entram como configuracao/fonte da organizacao, nao como metodo comercial hardcoded no provider Z-API.

## Fontes tecnicas

Documentacao oficial da Z-API consultada em 2026-08-30 e revisada em 2026-08-31:

- Security/Authentication: `https://developer.z-api.io/en/security/introduction`
- Envio de texto: `https://developer.z-api.io/message/send-text`
- Envio de imagem: `https://developer.z-api.io/message/send-message-image`
- Envio de audio: `https://developer.z-api.io/message/send-message-audio`
- Envio de documento: `https://developer.z-api.io/message/send-message-document`
- Status da instancia: `https://developer.z-api.io/instance/status`
- QR Code da instancia: `https://developer.z-api.io/instance/qr-code`
- Webhook de mensagens recebidas: `https://developer.z-api.io/en/webhooks/on-message-received`
- Exemplos de callbacks recebidos: `https://developer.z-api.io/en/webhooks/on-message-received-examples`
- Introducao de webhooks: `https://developer.z-api.io/en/webhooks/introduction`
- Account Security Token: `https://developer.z-api.io/en/security/client-token`

Contratos relevantes confirmados:

- autenticacao por URL `/instances/{instanceId}/token/{token}/...` e header `Client-Token`;
- `Client-Token` protege as requisicoes HTTP feitas pelo nosso backend para a API da Z-API, nao foi documentado como header enviado pela Z-API nos callbacks recebidos;
- envio de texto em `POST /send-text` com `phone` e `message`;
- envio de imagem em `POST /send-image`;
- envio de audio em `POST /send-audio`;
- envio de documento em `POST /send-document/{extension}`;
- status da instancia em `GET /status`;
- QR Code em `GET /qr-code`;
- configuracao de webhook recebido em `PUT /update-webhook-received` com `{"value": "<url>"}`; a documentacao exige URL HTTPS, mas nao documenta secret, signature ou header custom verificavel no callback `on-message-received`;
- callbacks de recebimento com `instanceId`, `messageId`, `phone`, `fromMe`, `momment`, `text`, `audio`, `image` e `document`;
- midias expostas pela Z-API devem ser tratadas como referencias temporarias, nao como armazenamento permanente autorizado.

## Regras herdadas

Esta feature preserva integralmente as regras das features `ai-whatsapp-channel` e `ai-whatsapp-evolution-provider`:

- `TEXT`, `AUDIO`, `IMAGE` e `DOCUMENT`;
- grounding e ausencia de resposta factual sem evidencia;
- `HUMAN_HANDOFF_REQUIRED`;
- `SCHEDULING_CONTEXT_ACTIVE` e nenhuma disponibilidade inventada;
- multi-tenant e cross-org protection;
- idempotencia, ordering e self-message protection;
- media retry;
- politica medica e prompt injection protection;
- RAG, Calendar e grounding continuam nos contratos existentes e nao devem ser redesenhados aqui.

## Historias

### US-056 — Provider Z-API atras do contrato de WhatsApp

Como equipe de produto, quero habilitar Z-API como provider intercambiavel, para validar conversas comerciais reais sem acoplar o runtime ao fornecedor.

#### AC-177 — Provider implementa o contrato existente

- **Dado** o contrato `WhatsAppProvider`
- **Quando** o provider Z-API e instanciado
- **Entao** ele oferece envio de texto, envio de midia, download de midia e marcacao de leitura sem exigir que o runtime conheca detalhes da Z-API

#### AC-178 — Configuracao vem somente de ambiente

- **Dado** um ambiente sandbox
- **Quando** a configuracao Z-API e carregada
- **Entao** os valores sao lidos de variaveis de ambiente e `.env.example` lista apenas nomes sem credenciais reais

#### AC-179 — Factory preserva todos os providers

- **Dado** a factory de WhatsApp
- **Quando** o provider solicitado e `meta`, `meta_cloud`, `evolution` ou `zapi`
- **Entao** a factory retorna o provider correto sem remover Meta ou Evolution

### US-057 — Envio outbound pela Z-API

Como atendente virtual, quero responder pelo WhatsApp via Z-API, para conduzir conversas comerciais no sandbox.

#### AC-180 — Texto outbound usa o endpoint oficial

- **Dado** uma mensagem textual de resposta
- **Quando** o provider Z-API envia a mensagem
- **Entao** ele chama `POST /instances/{instanceId}/token/{token}/send-text` com `Client-Token`, `phone` e `message`

#### AC-181 — Midia outbound usa endpoints oficiais

- **Dado** uma midia permitida
- **Quando** o provider Z-API envia imagem, audio ou documento
- **Entao** ele usa respectivamente `send-image`, `send-audio` ou `send-document/{extension}` sem expor detalhes ao runtime

#### AC-182 — Erros nao vazam segredos

- **Dado** uma falha de credencial ou indisponibilidade da Z-API
- **Quando** o erro e retornado para logs/runner
- **Entao** tokens, client tokens e secrets sao redigidos

### US-058 — Webhook Z-API normalizado

Como runtime de atendimento, quero receber eventos Z-API normalizados, para processar mensagens pelo mesmo adapter multi-provider.

#### AC-183 — Webhook legitimo sem secret nativo nao e rejeitado

- **Dado** um callback `on-message-received` da Z-API em JSON com `instanceId` conhecido
- **Quando** a requisicao chega sem header de secret customizado
- **Entao** o evento nao recebe 403 por ausencia de secret inexistente na documentacao; a seguranca fica em HTTPS, configuracao da URL na instancia, `instanceId` conhecido, isolamento por organizacao, idempotencia, self-message e validacao de payload

#### AC-184 — Eventos suportados sao normalizados

- **Dado** callbacks Z-API de texto, audio, imagem e documento
- **Quando** o webhook recebe os payloads oficiais
- **Entao** cada evento e convertido para o modelo interno `TEXT`, `AUDIO`, `IMAGE` ou `DOCUMENT`

#### AC-185 — Instancia desconhecida ou cruzada e bloqueada

- **Dado** um payload Z-API com `instanceId`
- **Quando** a instancia nao esta vinculada deterministicamente a uma organizacao conhecida
- **Entao** o webhook rejeita o evento e ignora qualquer `organizationId` vindo do payload/conteudo do paciente

#### AC-186 — Idempotencia, ordering e self-message continuam ativos

- **Dado** callbacks duplicados, fora de ordem ou enviados pela propria instancia
- **Quando** o adapter processa os eventos normalizados
- **Entao** duplicatas sao suprimidas, historico preserva a ordem processada e mensagens proprias nao acionam o runtime

### US-059 — Midias Z-API seguem a politica existente

Como equipe de atendimento, quero que audio, imagem e documento da Z-API sigam as politicas ja aprovadas, para nao criar riscos clinicos ou operacionais.

#### AC-187 — Midia recebida e obtida sem tratar URL temporaria como fonte permanente

- **Dado** uma referencia de midia recebida da Z-API
- **Quando** o provider baixa o conteudo
- **Entao** ele usa a referencia temporaria apenas para obtencao da midia e preserva metadata/proveniencia separadamente

#### AC-188 — Audio entra no STT e pode pedir retry

- **Dado** um audio recebido pela Z-API
- **Quando** o conteudo e audivel
- **Entao** o transcript entra no runtime; se inaudivel, a decisao e `MEDIA_RETRY_REQUIRED`

#### AC-189 — Imagem clinica ou ambigua gera handoff

- **Dado** uma imagem recebida pela Z-API
- **Quando** ela e clinica, ambigua ou nao compreendida administrativamente
- **Entao** a decisao e `HUMAN_HANDOFF_REQUIRED`

#### AC-190 — Documento preserva proveniencia e politica

- **Dado** um documento recebido pela Z-API
- **Quando** ele e processado
- **Entao** filename, MIME, provider media ID, referencia/storage e texto extraido sao preservados; documento clinico, corrompido ou ilegiveil gera `HUMAN_HANDOFF_REQUIRED`

### US-060 — Runner sandbox Z-API

Como operador do sandbox, quero comandos locais para preparar e validar a instancia Z-API, para fazer o primeiro teste real sem misturar credenciais com codigo.

#### AC-191 — Status da instancia e verificavel

- **Dado** credenciais Z-API configuradas
- **Quando** o runner consulta status
- **Entao** ele chama o endpoint oficial de status da instancia

#### AC-192 — QR Code/conexao e verificavel quando suportado

- **Dado** credenciais Z-API configuradas
- **Quando** o runner solicita QR Code
- **Entao** ele chama o endpoint oficial de QR Code e redige informacoes sensiveis

#### AC-193 — Webhook recebido pode ser configurado

- **Dado** uma URL HTTPS publica de sandbox
- **Quando** o runner configura webhook
- **Entao** ele chama `update-webhook-received` com a URL de recebimento Z-API

#### AC-194 — Falta de credenciais bloqueia com nomes seguros

- **Dado** credenciais Z-API ausentes
- **Quando** o smoke sandbox e executado
- **Entao** ele retorna `BLOCKED_MISSING_CREDENTIALS` e imprime apenas os nomes das variaveis faltantes

#### AC-195 — LIVE_VERIFIED exige chamadas reais

- **Dado** a lista de cenarios live Z-API
- **Quando** o runner ainda nao executou chamadas reais de status/webhook/outbound/inbound
- **Entao** ele nao marca `LIVE_VERIFIED`

### US-061 — Compatibilidade com o ecossistema existente

Como mantenedor, quero adicionar Z-API sem regressao dos providers existentes, para preservar o caminho oficial Meta e o sandbox Evolution.

#### AC-196 — Meta e Evolution continuam testados

- **Dado** os providers Meta e Evolution existentes
- **Quando** a suite do WhatsApp roda
- **Entao** suas selecoes, parsers e comportamentos essenciais continuam passando

#### AC-197 — CRM nao e iniciado e contratos centrais nao sao redesenhados

- **Dado** esta feature de provider WhatsApp
- **Quando** a implementacao e concluida
- **Entao** nao ha inicio de CRM nem alteracao funcional em RAG, Calendar ou grounding fora do necessario para integrar o provider

### US-062 — Callback Z-API usa o runtime conversacional real

Como operador do sandbox live, quero que mensagens reais recebidas pela Z-API atravessem o runtime conversacional completo, para que o paciente receba uma resposta comercial contextual e nao um acknowledgement generico.

#### AC-198 — Texto inbound alcanca runtime e resposta outbound vem dele

- **Dado** um callback Z-API `ReceivedCallback` de texto com `instanceId` conhecido
- **Quando** o webhook processa a mensagem
- **Entao** o adapter chama o runtime com `organizationId`, `conversationId`, contato e texto, e a mensagem outbound usa o texto gerado pelo runtime em vez do placeholder `Certo, vou seguir com seu atendimento.`

#### AC-199 — Turnos consecutivos preservam estado conversacional

- **Dado** tres mensagens sequenciais do mesmo telefone na mesma instancia Z-API
- **Quando** elas sao processadas pelo webhook
- **Entao** a mesma conversa e reutilizada, cada chamada do runtime recebe o historico anterior e as respostas nao sao todas identicas

#### AC-200 — Identidades diferentes nao compartilham historico

- **Dado** mensagens de contatos ou organizacoes diferentes
- **Quando** o adapter resolve as conversas
- **Entao** cada contato/organizacao tem `conversationId` e historico separados, sem vazamento cross-org

#### AC-201 — Falha do runtime nao e mascarada como sucesso

- **Dado** uma falha tecnica no runtime durante o processamento de texto inbound
- **Quando** o webhook tenta responder
- **Entao** a falha e registrada com stage sanitizado e a resposta generica de sucesso nao e enviada como se a IA tivesse funcionado

#### AC-202 — Caminho live emite observabilidade segura por estagio

- **Dado** uma mensagem live Z-API
- **Quando** ela atravessa webhook, normalizacao, resolucao, runtime, grounding e outbound
- **Entao** logs seguros registram `webhook_received`, `message_normalized`, `organization_resolved`, `conversation_resolved`, `runtime_started`, `retrieval_completed`, `model_called`, `grounding_result`, `response_generated` e `outbound_sent` sem secrets

### US-063 — Diagnostico live separa falhas HTTP por provider

Como operador do sandbox live, quero que erros HTTP dentro do runtime Z-API indiquem o provider e o estagio exato, para corrigir falhas reais sem fallback generico e sem expor secrets.

#### AC-203 — Retrieval Supabase registra 400 com corpo seguro

- **Dado** o retrieval live Z-API recebendo uma resposta HTTP 400 do Supabase
- **Quando** a busca falha antes da chamada ao modelo
- **Entao** o log registra `retrieval_started` e `retrieval_failed` com provider `supabase`, status HTTP, endpoint logico e corpo/codigo sanitizados

#### AC-204 — Organizacao sandbox Z-API usa UUID persistido no Supabase

- **Dado** `ZAPI_ORGANIZATION_ID=sandbox-org-dr-leonardo-carvalho`
- **Quando** o servidor live Z-API construi o resolver
- **Entao** ele mapeia a instancia para o UUID deterministico persistido pelo sandbox Supabase, evitando filtro invalido em coluna `uuid`

#### AC-205 — Chamada OpenAI registra inicio e falha especifica

- **Dado** o runtime Z-API chegando a chamada do modelo
- **Quando** a Responses API devolve erro HTTP
- **Entao** o log registra `model_call_started` e `model_call_failed` com provider `openai`, status HTTP, endpoint logico e corpo/codigo sanitizados

#### AC-206 — Falha HTTP nao e mascarada como stage runtime generico

- **Dado** uma falha HTTP em retrieval ou modelo
- **Quando** o webhook processa texto inbound
- **Entao** a resposta HTTP do webhook e 500, nenhuma mensagem generica e enviada, e os logs preservam o estagio especifico antes de `runtime_failed`

#### AC-207 — Configuracao live lida pelo servidor e compativel com sandboxes

- **Dado** o `.env` usado pelo processo Z-API
- **Quando** o servidor inicializa
- **Entao** ele usa os mesmos nomes de variaveis dos sandboxes live para OpenAI e Supabase e nao exige novo secret de webhook inbound

### US-064 — Servidor live Z-API nao importa componentes opcionais de sandbox

Como operador do live Z-API, quero iniciar o servidor sem instalar dependencias opcionais de smoke sandbox, para que o caminho WhatsApp nao quebre por acoplamento acidental a LangSmith.

#### AC-208 — Importar zapi_server nao exige langsmith

- **Dado** um ambiente sem pacote `langsmith`
- **Quando** `ai_agent_runtime.whatsapp.zapi_server` e importado
- **Entao** o import nao carrega `ai_agent_runtime.sandbox` nem exige `langsmith`

#### AC-209 — UUIDs deterministico permanecem identicos

- **Dado** ids logicos de sandbox existentes
- **Quando** sandbox e live Z-API calculam os ids persistidos
- **Entao** ambos usam o mesmo modulo neutro e preservam os UUIDs deterministas ja usados

### US-065 — Turnos live Z-API sao exatamente-uma-vez e grounded

Como operador do sandbox WhatsApp, quero que cada callback inbound acione o runtime no maximo uma vez e que respostas factuais sem evidencia sejam bloqueadas, para preservar continuidade conversacional sem alucinacao.

#### AC-210 — Um inbound gera uma invocacao de runtime e no maximo um outbound

- **Dado** um callback Z-API valido e nao duplicado
- **Quando** o adapter processa o evento
- **Entao** ha exatamente uma `runtimeInvocationId`, uma chamada ao runtime e no maximo uma mensagem outbound

#### AC-211 — Segundo turno reutiliza conversa e carrega historico

- **Dado** dois callbacks Z-API com `messageId` distintos do mesmo contato
- **Quando** ambos sao processados em ordem
- **Entao** eles nao sao tratados como duplicatas, reutilizam a mesma `conversationId` e o segundo runtime recebe o historico do primeiro

#### AC-212 — Callback duplicado, fromMe e fora de ordem continuam protegidos

- **Dado** callback repetido, callback `fromMe` ou callback mais antigo que o ultimo turno processado
- **Quando** o adapter processa o evento
- **Entao** registra `duplicate_detected`, `self_message_ignored` ou `ordering_rejected` e nao chama o runtime novamente

#### AC-213 — Claim factual com evidencia zero nao passa grounding

- **Dado** uma resposta gerada que contem afirmacao factual sobre clinica, procedimento, preco, agenda ou tratamento
- **Quando** `evidenceCount=0`
- **Entao** `grounding_result.passed=false` e a decisao final e `HUMAN_HANDOFF_REQUIRED`

#### AC-214 — Resposta conversacional sem claim factual pode passar sem evidencia

- **Dado** uma resposta puramente conversacional ou de qualificacao que nao afirma fatos da clinica/procedimento
- **Quando** `evidenceCount=0`
- **Entao** `grounding_result.passed=true` e a conversa pode continuar

#### AC-215 — Logs de ciclo de vida tornam descartes visiveis

- **Dado** callbacks Z-API live
- **Quando** sao recebidos, descartados ou processados
- **Entao** os logs seguros incluem `inbound_received`, `duplicate_detected`, `self_message_ignored`, `ordering_rejected`, `conversation_history_loaded`, `history_turn_count`, `runtime_invocation_id` e `outbound_sent` quando aplicavel

### US-066 — Retrieval e historico live Z-API persistentes

Como operador do sandbox WhatsApp, quero que o caminho live recupere conhecimento publicado por termo relevante e preserve historico entre reinicios locais, para validar conversas reais sem perder contexto nem enfraquecer grounding.

#### AC-216 — Retrieval Dr. Leonardo encontra briefing publicado quando a base suporta

- **Dado** chunks publicados e processados da Clinica Carvalho e Tavares contendo termos do briefing como `implante`, `Scanner Virtuo`, `Hospital da Bahia`, `Matatu` ou `pagamento`
- **Quando** o runtime live recebe mensagens comerciais sobre esses termos
- **Entao** o retrieval lexical usa termos relevantes da consulta e retorna evidencia autorizada da organizacao do Dr. Leonardo

#### AC-217 — Retrieval nao cruza organizacao ou versao inelegivel

- **Dado** chunks de outra organizacao ou versoes nao publicadas/processadas
- **Quando** o retrieval live consulta termos presentes no briefing do Dr. Leonardo
- **Entao** somente chunks da organizacao solicitada, publicados e processados podem entrar como evidencia

#### AC-218 — Primeiro turno e persistido no sandbox live

- **Dado** um callback Z-API valido
- **Quando** o primeiro turno e processado pelo servidor live
- **Entao** `conversationId`, mensagem inbound e resposta outbound sao gravados em store local de sandbox

#### AC-219 — Segundo turno carrega historico persistido

- **Dado** um novo processo/store apontando para o mesmo arquivo local
- **Quando** chega o segundo callback do mesmo contato e instancia
- **Entao** o runtime recebe o historico do primeiro turno e reutiliza o mesmo `conversationId`

#### AC-220 — Terceiro turno carrega historico crescente

- **Dado** dois turnos anteriores persistidos
- **Quando** chega o terceiro callback do mesmo contato e instancia
- **Entao** o historico carregado contem os turnos anteriores e continua crescendo sem duplicar mensagens

#### AC-221 — Comportamento de restart fica explicito

- **Dado** o store persistente local do sandbox live
- **Quando** o servidor e reiniciado com o mesmo caminho de store
- **Entao** o historico e preservado; ao usar um caminho novo ou apagar o arquivo, o sandbox inicia sem historico anterior

#### AC-222 — Grounding sem evidencia continua bloqueando factual

- **Dado** uma resposta factual sem evidencia recuperada
- **Quando** o grounding live avalia a resposta
- **Entao** a decisao permanece `HUMAN_HANDOFF_REQUIRED` com `UNSUPPORTED_FACTUAL_CLAIM`

### US-083 — Z-API sandbox usa Dr. Leonardo como cliente de teste

Como operador do sandbox comercial, quero substituir a organizacao ficticia principal pelo primeiro cliente real de teste, para validar conversao com dados autorizados sem usar pacientes reais.

#### AC-280 — Z-API default aponta para Dr. Leonardo

- **Dado** configuracao Z-API sem override local
- **Quando** `ZApiWhatsAppConfig` e carregada
- **Entao** `organization_id` usa `sandbox-org-dr-leonardo-carvalho`.

#### AC-281 — Dataset sandbox contem Dr. Leonardo e Boreal

- **Dado** o dataset de sandbox
- **Quando** ele e inspecionado
- **Entao** a organizacao principal e `Clinica Carvalho e Tavares Odontologia Integrada`
- **E** a organizacao secundaria `Clinica Boreal Sandbox` permanece para prova cross-org.

#### AC-282 — Catalogo do briefing nao e fechado sem prova

- **Dado** os procedimentos informados no briefing do Dr. Leonardo
- **Quando** o catalogo e carregado
- **Entao** ele usa `knowledgeMode=OPEN_WORLD` e `closedWorldCompletenessApproved=false`
- **E** ausencia de procedimento nao gera `NOT_OFFERED`.

#### AC-283 — Configuracao organizacional nao inventa identidade

- **Dado** variaveis autorizadas da organizacao
- **Quando** o prompt comercial e montado
- **Entao** nome da clinica, profissional, horarios e unidades podem ser incluídos
- **E** nome da assistente/paciente nao e inferido a partir desses dados.

#### AC-284 — Urgencia clinica exige handoff antes do modelo

- **Dado** mensagem com dor intensa, sangramento, trauma, pos-procedimento, medicacao ou tema clinico sensivel
- **Quando** o turno e classificado
- **Entao** a decisao e `HUMAN_HANDOFF_REQUIRED` antes de chamada ao modelo.

#### AC-285 — Handoff clinico e silencioso no Z-API

- **Dado** handoff clinico exigido
- **Quando** o adapter processa o callback Z-API
- **Entao** nenhuma resposta autonoma e enviada ao paciente e o contexto fica preservado para humano.

### US-085 — Base Dr. Leonardo tem paridade entre dataset local e Supabase live

Como operador do sandbox Z-API, quero que o runtime live recupere no Supabase a mesma base do Dr. Leonardo usada nos testes locais, para evitar falsa seguranca quando o dataset existe no codigo mas nao no banco.

#### AC-291 — Retrieval semeado gera resposta grounded e outbound

- **Dado** documentos, versoes, chunks e embeddings do Dr. Leonardo semeados em Supabase sandbox
- **Quando** a mensagem `Oi, perdi um dente e queria saber mais sobre implante` e processada
- **Entao** o retrieval retorna pelo menos um chunk da organizacao do Dr. Leonardo
- **E** a resposta factual suportada passa grounding e gera `outbound_sent`.

#### AC-292 — Configuracao autorizada fundamenta abertura

- **Dado** `assistant_name`, `assistant_role`, `clinic_name`, `doctor_name`, `locations` ou `business_hours` configurados pela organizacao
- **Quando** a resposta de abertura usa apenas esses valores configurados
- **Entao** o grounding aceita a resposta como `RESPONSE_CONSTRAINED_BY_AUTHORIZED_CONFIG`, mesmo com retrieval zero no turno.

#### AC-293 — Configuracao nao substitui RAG para procedimento

- **Dado** configuracao organizacional valida
- **Quando** a resposta afirma fato de procedimento, preco, pagamento, tecnica, resultado ou politica nao presente em evidencia recuperada
- **Entao** o grounding continua reprovando com `UNSUPPORTED_FACTUAL_CLAIM`.

### US-067 — Runtime live Z-API conduz venda sem virar FAQ

Como operador do sandbox comercial, quero que o caminho live Z-API trate interesse inicial em procedimento oferecido como conversa de venda progressiva, para validar qualidade comercial sem inventar fatos nem gerar handoff desnecessario.

#### AC-228 — Procedimento oferecido continua conversa comercial

- **Dado** um catalogo de teste publicado contendo o procedimento perguntado
- **Quando** o paciente diz `Quero saber mais sobre botox`
- **Entao** o runtime nao gera handoff por retrieval zero isolado
- **E** orienta o modelo a conduzir com uma pergunta comercial principal em vez de iniciar por explicacao enciclopedica.

#### AC-229 — Procedimento ausente em catalogo fechado gera negativa autorizada

- **Dado** um catalogo fechado completo sem `transplante capilar`
- **Quando** o paciente pergunta se a clinica faz transplante capilar
- **Entao** o runtime responde que nao oferece, sem handoff e sem inventar alternativa.

#### AC-230 — Atributo factual ausente gera handoff silencioso

- **Dado** Botox existe no catalogo, mas marca da toxina nao existe em fonte autorizada
- **Quando** o paciente pergunta `Qual marca de botox voces usam?`
- **Entao** a decisao e `HUMAN_HANDOFF_REQUIRED`
- **E** o adapter Z-API nao envia mensagem ao paciente.

### US-070 — Relacao de turno evita handoff falso em respostas curtas

Como operador do sandbox comercial, quero que o runtime interprete respostas curtas pelo contexto da pergunta anterior da IA, para evitar que palavras ambiguas virem perguntas factuais isoladas.

#### AC-235 — Resposta sobre marcas visiveis nao vira atributo de brand

- **Dado** a IA perguntou se as linhas aparecem ao movimentar ou se marcas ja ficam visiveis em repouso
- **Quando** o paciente responde `marcas que ja ficam visiveis`
- **Entao** o runtime registra `turn_relation=ANSWER_TO_PREVIOUS_QUESTION`
- **E** `requires_evidence=false`
- **E** nao gera `HUMAN_HANDOFF_REQUIRED`.

#### AC-236 — Pergunta sobre marca de Botox continua factual

- **Dado** Botox existe no catalogo, mas a marca/fabricante nao existe em evidencia autorizada
- **Quando** o paciente pergunta `Qual marca de botox voces usam?`
- **Entao** o runtime registra `interpreted_intent=ATTRIBUTE_QUERY`
- **E** `requires_evidence=true`
- **E** gera handoff silencioso sem outbound.

#### AC-237 — Escolhas e confirmacoes curtas usam a pergunta anterior

- **Dado** a IA fez uma pergunta de escolha, interesse ou qualificacao
- **Quando** o paciente responde `testa`, `sim`, `nao`, `quero fazer em breve` ou texto curto equivalente
- **Entao** a classificacao considera o turno como resposta contextual
- **E** a venda continua sem exigir retrieval.

#### AC-238 — Retrieval zero nao implica handoff em descricao do paciente

- **Dado** o retrieval retorna zero chunks para uma descricao de necessidade ou incomodo do paciente
- **Quando** nao ha pergunta factual nem claim factual sobre a clinica
- **Entao** o runtime permite continuidade comercial sem handoff.

#### AC-239 — Logs seguros expõem classificacao comportamental

- **Dado** qualquer turno processado pelo runtime live Z-API
- **Quando** a classificacao comportamental for executada
- **Entao** os logs incluem `turn_relation`, `interpreted_intent`, `conversation_stage`, `requires_evidence`, `handoff_decision`
- **E** incluem `unsupported_attribute_reason` somente quando aplicavel.

### US-072 — Grounding diferencia pedido factual do paciente de erro de geracao

Como operador do sandbox comercial, quero que o runtime separe fato solicitado pelo paciente de claim factual introduzida pelo modelo, para manter o grounding forte sem interromper vendas por alucinacao recuperavel.

#### AC-242 — Claim factual introduzida pelo modelo e regenerada com seguranca

- **Dado** um turno contextual de qualificacao com `user_requires_evidence=false` e retrieval sem evidencias
- **Quando** a primeira resposta gerada contem claim factual sem suporte
- **Entao** o runtime rejeita essa resposta, nao faz handoff, regenera uma vez em modo `CONVERSATIONAL_NO_FACTS` e envia apenas a resposta conversacional grounded.

#### AC-243 — Retry alucinado nao envia resposta insegura

- **Dado** um turno contextual de qualificacao com `user_requires_evidence=false`
- **Quando** a geracao inicial e o retry seguro ainda contem claim factual sem suporte
- **Entao** nenhum outbound factual e enviado, nao ha loop de retry e a falha e tratada como falha interna de geracao, nao como pedido factual do paciente.

#### AC-244 — Pedido factual sem suporte continua handoff silencioso

- **Dado** uma pergunta factual ou de atributo que exige evidencia autorizada
- **Quando** a evidencia necessaria nao esta disponivel
- **Entao** a decisao permanece `HUMAN_HANDOFF_REQUIRED`, sem retry conversacional para contornar a falta de informacao.

#### AC-245 — Logs distinguem evidencia exigida pelo turno e pela resposta

- **Dado** uma resposta gerada que falha grounding
- **Quando** o runtime decide entre handoff e regeneracao
- **Entao** os logs incluem `turn_requires_evidence`, `response_requires_evidence`, `grounding_failed` e `grounding_failure_origin` com origem `USER_REQUESTED_UNSUPPORTED_FACT` ou `MODEL_INTRODUCED_UNSUPPORTED_FACT`.

#### AC-246 — Interesse inicial prioriza descoberta comercial

- **Dado** a mensagem `Quero saber mais sobre botox` classificada como interesse/descoberta
- **Quando** ha evidencia RAG disponivel
- **Entao** o modelo e instruido a priorizar qualificacao comercial com uma pergunta principal, sem iniciar obrigatoriamente por explicacao tecnica enciclopedica.

#### AC-247 — Retry seguro nao expõe termos internos nem fatos da clinica

- **Dado** uma regeneracao `CONVERSATIONAL_NO_FACTS`
- **Quando** o prompt de retry e montado
- **Entao** ele proibe fatos sobre clinica, medico, procedimento, preco, resultado, tecnica, duracao ou agenda sem evidencia, e proibe mencionar RAG, retrieval, base, falta de evidencia, equipe ou handoff ao paciente.

#### AC-248 — Fato suportado continua podendo responder grounded

- **Dado** uma pergunta factual cuja evidencia autorizada esta disponivel
- **Quando** a resposta gerada usa essa evidencia
- **Entao** o grounding passa, nao ha handoff e nenhuma regeneracao segura e acionada.

### US-086 — Conversa comercial live preserva contexto progressivo

Como operador do sandbox comercial Z-API, quero que respostas curtas em conversa real sejam resolvidas pelo historico e pelo estado comercial, para evitar perda de contexto, retrieval vazio e tom robotico.

#### AC-294 — Estado comercial aprende necessidade progressiva

- **Dado** a conversa `Quero saber sobre implante` → `Substituir um dente` → `Tenho medo de fazer` → `Os dois`
- **Quando** cada webhook e processado
- **Entao** `commercialState.patient_need_summary` preserva interesse em implante, situacao de substituir dente perdido, objecao de medo e topicos de medo do procedimento e pos-operatorio
- **E** `discovery_depth` e `discovery_information_gain` ficam maiores que zero.

#### AC-295 — Respostas curtas sao resolvidas pelo contexto

- **Dado** a IA perguntou se o medo esta ligado ao procedimento ou ao pos-operatorio
- **Quando** o paciente responde `Os dois`
- **Entao** o turno e marcado como resposta curta contextual resolvida
- **E** a proxima acao nao perde o interesse anterior em implante.

#### AC-296 — Retrieval live usa query contextual

- **Dado** um turno curto como `Os dois`
- **Quando** ha historico e estado comercial com interesse e objecao
- **Entao** o retrieval consulta termos contextuais como implante, medo, procedimento e pos-operatorio
- **E** nao consulta apenas a mensagem curta isolada.

#### AC-297 — Evidencia recente pode ser reaproveitada sem cruzar organizacao

- **Dado** uma conversa com evidencia autorizada ja recuperada no mesmo `conversationId` e `organizationId`
- **Quando** o turno seguinte e diretamente relevante ao mesmo escopo
- **Entao** o runtime pode reaproveitar a evidencia recente de forma auditavel
- **E** evidencia de outra organizacao nunca e aceita.

#### AC-298 — Grounding permanece obrigatorio

- **Dado** retrieval contextual ou evidencia reaproveitada
- **Quando** a resposta gerada contem fatos sobre clinica, procedimento ou diferencial
- **Entao** o grounding valida a resposta antes do envio
- **E** fatos sem evidencia continuam bloqueados.

#### AC-299 — Naturalidade evita eco e formulario

- **Dado** uma conversa comercial multi-turno
- **Quando** a resposta e gerada
- **Entao** o prompt instrui anti-eco, uma pergunta principal, sem menus A/B/C recorrentes, sem escolha forcada e sem empatia performatica padrao.

#### AC-300 — Runtime completa resposta sem regeneracao insegura

- **Dado** o turno contextual `Os dois` com evidencia contextual disponivel
- **Quando** a resposta e gerada e grounded
- **Entao** existe outbound enviado
- **E** nao ocorre `CONVERSATIONAL_REGENERATION_UNGROUNDED`.

### US-088 — Batching de mensagens consecutivas por conversa

Como operador do sandbox WhatsApp, quero agrupar mensagens inbound consecutivas da mesma conversa antes de chamar o runtime, para responder ao turno logico completo do paciente sem iniciar multiplas execucoes para fragmentos enviados em sequencia.

#### AC-310 — Debounce reinicia por mensagem e flush ocorre apos silencio

- **Dado** mensagens inbound da mesma organizacao, provider account e conversa em `t=0s`, `t=2s` e `t=4s`
- **Quando** nenhuma nova mensagem chega
- **Entao** um unico lote e processado por volta de `t=10s`, 6000ms apos a ultima mensagem
- **E** o runtime e chamado uma unica vez.

#### AC-311 — Max wait encerra lote sem espera indefinida

- **Dado** mensagens inbound da mesma conversa continuam chegando dentro da janela de debounce
- **Quando** passam 12000ms desde a primeira mensagem do lote
- **Entao** o lote e processado por `MESSAGE_BATCH_MAX_WAIT_MS`
- **E** novas mensagens passam a compor o proximo lote.

#### AC-312 — Mensagem unica respeita debounce padrao

- **Dado** uma unica mensagem inbound
- **Quando** passam 6000ms sem nova mensagem
- **Entao** o runtime processa um unico turno logico
- **E** envia no maximo um outbound.

#### AC-313 — Lock impede runtime concorrente na mesma conversa

- **Dado** um lote esta em execucao no runtime
- **Quando** chega nova mensagem da mesma conversa
- **Entao** nenhuma segunda execucao concorrente e iniciada
- **E** a mensagem fica em pending batch para processamento posterior.

#### AC-314 — Conversas diferentes processam independentemente

- **Dado** mensagens de duas conversas diferentes
- **Quando** as janelas de debounce vencem
- **Entao** cada conversa pode adquirir seu proprio lock e processar independentemente.

#### AC-315 — Lote preserva IDs, timestamps e ordem

- **Dado** um lote com multiplas mensagens inbound
- **Quando** o turno logico e criado
- **Entao** `providerMessageIds`, timestamps e textos originais ficam preservados em ordem
- **E** o texto operacional nao altera o sentido das mensagens.

#### AC-316 — Early flush exige gatilho deterministico sem negacao

- **Dado** mensagem com gatilho claro de handoff seguro
- **Quando** o conteudo nao estiver negado pelo paciente
- **Entao** o lote pode ser encerrado antes do debounce
- **E** `nao estou sangrando` nao dispara early flush por conter a palavra `sangrando`.

#### AC-317 — Observabilidade de batching e lock

- **Dado** batching habilitado no caminho live
- **Quando** mensagens sao enfileiradas, agregadas, processadas ou bloqueadas por lock
- **Entao** os logs incluem `message_batch_started`, `message_batch_message_added`, `message_batch_debounce_reset`, `message_batch_max_wait_reached`, `message_batch_flushed`, `message_batch_size`, `message_batch_age_ms`, `logical_patient_turn_created`, `conversation_lock_acquired`, `conversation_lock_released` e `queued_inbound_count`.

### US-091 — Z-API aplica conduta comercial global no caminho live

Como operador do sandbox Z-API, quero que o caminho live use as novas regras comerciais globais, para que conversas reais nao exponham lacunas internas nem percam dados do canal.

#### AC-330 — Resposta com lacuna interna e bloqueada antes do outbound

- **Dado** uma resposta gerada contendo frase como nao consigo confirmar por aqui, nao tenho informacao ou nao encontrei na base
- **Quando** o grounding live valida a resposta
- **Entao** a resposta falha com motivo `INTERNAL_KNOWLEDGE_GAP_EXPOSED` e nao e enviada diretamente ao paciente.

#### AC-331 — Lacuna interna de geracao pode regenerar resposta comercial segura

- **Dado** uma pergunta factual em que ha evidencia autorizada para ponte comercial, mas nao para o atributo tecnico exato
- **Quando** o modelo tenta expor a lacuna
- **Entao** o runtime trata a falha como geracao do modelo, tenta uma regeneracao curta sem fatos novos e envia no maximo uma resposta aprovada pelo grounding.

#### AC-332 — Telefone do canal chega ao estado operacional do runtime Z-API

- **Dado** um callback Z-API com `phone` normalizado como `contactExternalId`
- **Quando** o adapter cria o contexto do runtime
- **Entao** `channelContactExternalId` e disponibilizado ao playbook para preencher `patient_phone` sem perguntar o WhatsApp novamente.

### US-092 — Base Dr. Leonardo publica nova versao do briefing com avaliacao gratuita

Como operador do sandbox comercial, quero substituir a versao anterior do briefing do Dr. Leonardo por uma nova fonte autorizada, para remover a ambiguidade sobre gratuidade da avaliacao sem enfraquecer grounding.

#### AC-344 — Dataset aponta para a nova fonte autorizada

- **Dado** o dataset sandbox do Dr. Leonardo
- **Quando** a fonte documental e inspecionada
- **Entao** todos os documentos da organizacao usam `BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf`
- **E** a versao do dataset indica `v2`.

#### AC-345 — Publicacao supersede a versao anterior

- **Dado** a persistencia live no Supabase
- **Quando** o pipeline publica a nova versao do briefing
- **Entao** a versao `v1` do mesmo documento fica `SUPERSEDED` e nao processavel
- **E** apenas a versao `v2` fica `PUBLISHED` e `processing_valid=true` para retrieval current.

#### AC-346 — Avaliacao gratuita responde com grounding

- **Dado** evidencia current contendo `Avaliacao gratuita` para casos de busca por procedimento
- **Quando** o paciente pergunta `avaliacao e gratuita`, `quanto custa a avaliacao`, `consulta e de graca` ou `qual valor da avaliacao`
- **Entao** a resposta factual pode afirmar que a avaliacao e gratuita
- **E** nao exige handoff.

#### AC-347 — Preco de procedimento nao e inventado

- **Dado** evidencia current contendo que valores dos procedimentos sao informados apos avaliacao
- **Quando** o paciente pergunta `quanto custa o implante` ou `quanto custa lente`
- **Entao** a resposta nao inventa valor de procedimento
- **E** informa que o valor e definido/informado apos avaliacao, mantendo a avaliacao gratuita quando aplicavel.

#### AC-348 — Ambiguidade antiga nao aparece em resposta current

- **Dado** a nova versao current autoriza avaliacao gratuita
- **Quando** o grounding valida uma resposta sobre avaliacao
- **Entao** frases como `precisa confirmar`, `pode nao ser cobrada`, `depende do caso` ou `a clinica confirma antes` sao rejeitadas como ambiguidade obsoleta.

#### AC-349 — Chunks antigos nao entram no retrieval atual

- **Dado** chunks da versao anterior permanecem no banco para rastreabilidade
- **Quando** o retrieval live consulta a organizacao do Dr. Leonardo
- **Entao** apenas chunks ligados a `document_versions` `PUBLISHED` e `processing_valid=true` podem entrar como evidencia.

#### AC-350 — Isolamento cross-org permanece intacto

- **Dado** a nova versao do briefing do Dr. Leonardo e documentos de outra organizacao
- **Quando** o retrieval consulta qualquer termo de avaliacao, implante, lentes ou pagamento
- **Entao** nenhum chunk de outra organizacao entra como evidencia.

### US-093 — Segundo turno operacional nao morre por falha transitoria de retrieval

Como operador do sandbox comercial Z-API, quero que respostas operacionais como `Sim` avancem o agendamento sem depender de RAG desnecessario, para que falhas transitorias do Supabase nao silenciem uma conversa que ja tem proximo passo deterministico.

#### AC-351 — Falha transitoria de Supabase recebe retry limitado

- **Dado** uma busca factual live no Supabase que falha temporariamente com connection reset, timeout, erro temporario, HTTP 429 ou HTTP 5xx
- **Quando** o retrieval e executado
- **Entao** o runtime tenta novamente com backoff pequeno e limitado
- **E** registra `retrieval_retry_started`, `retrieval_retry_attempt`, `retrieval_retry_succeeded` ou `retrieval_retry_exhausted` conforme o resultado.

#### AC-352 — Erro deterministico de retrieval nao recebe retry

- **Dado** o Supabase retorna erro de autenticacao, permissao, query invalida ou schema
- **Quando** o retrieval falha
- **Entao** o runtime nao executa retry infinito nem mascara a falha como sucesso.

#### AC-353 — Turno operacional pode pular retrieval

- **Dado** a assistente perguntou se o paciente quer solicitar horario de avaliacao
- **Quando** o paciente responde afirmativamente com `sim`, `quero`, `pode`, `vamos`, `claro` ou equivalente
- **Entao** o runtime classifica o turno como operacional/conversacional, registra `TURN_EVIDENCE_REQUIREMENT` como sem necessidade de RAG e nao chama Supabase para interpretar essa aceitacao.

#### AC-354 — Confirmacao ao CTA avanca scheduling de forma deterministica

- **Dado** `previous_assistant_action=PROPOSE_APPOINTMENT` inferido pela pergunta anterior e o paciente responde afirmativamente
- **Quando** unidade, data ou horario ainda faltam
- **Entao** `appointment_intent=true`, `next_best_action=SCHEDULE`, `scheduling_state=COLLECTING_REQUIRED_DATA` e a resposta pede o dado faltante adequado sem inventar disponibilidade.

#### AC-355 — Query factual com retrieval indisponivel nao inventa fato

- **Dado** uma pergunta factual ou de preco cujo retrieval falha mesmo apos retries
- **Quando** nao ha evidencia autorizada
- **Entao** o runtime nao inventa resposta factual e produz um desfecho seguro controlado.

#### AC-356 — Estado de medo vem somente do paciente

- **Dado** a assistente menciona `medo do procedimento` ou `procedimento` em uma pergunta
- **Quando** o paciente apenas responde `sim` sem ter declarado medo, receio ou risco
- **Entao** `objection_state` nao vira `FEAR_OR_RISK` e `fear_topics` fica ausente.

#### AC-357 — Medo explicito do paciente continua sendo capturado

- **Dado** o paciente diz explicitamente `tenho medo do procedimento`
- **Quando** o playbook comercial atualiza o estado
- **Entao** `objection_state=FEAR_OR_RISK` e o resumo preserva o topico de medo com proveniencia do paciente.

#### AC-358 — Memoria comercial nao cruza conversas

- **Dado** uma conversa A com medo declarado pelo paciente e uma conversa B sem medo declarado
- **Quando** ambas sao processadas no mesmo store
- **Entao** a conversa B nao herda `fear_topics`, `objection_state` nem memoria operacional da conversa A.

#### AC-359 — Falha do runtime no batching nao mata a thread de processamento

- **Dado** um lote em execucao falha dentro do runtime
- **Quando** o batch processor recebe a excecao
- **Entao** ele registra `batch_processing_failed`, libera o lock da conversa, registra recuperacao quando aplicavel e permite que a proxima mensagem seja processada.

### US-094 — Memoria operacional comercial no live WhatsApp

Como operador do sandbox comercial Z-API, quero que a conversa preserve estado operacional explicito entre turnos, para que a IA pareca natural, nao repita fatos ja respondidos e avance o agendamento sem voltar para descoberta.

#### AC-360 — Apresentacao depende de estado explicito

- **Dado** uma conversa nova com `assistant_introduced=false`
- **Quando** o primeiro turno real e processado
- **Entao** `should_introduce=true` mesmo que exista historico inconsistente
- **E** o estado `assistant_introduced` passa a ser persistido somente apos outbound efetivamente enviado.

#### AC-361 — Apresentacao nao se repete na mesma conversa

- **Dado** `assistant_introduced=true` em metadata persistida do mesmo `conversationId` e `organizationId`
- **Quando** novo turno e processado
- **Entao** `should_introduce=false` e a resposta nao deve repetir apresentacao inicial.

#### AC-362 — Fatos ja respondidos ficam em memoria factual

- **Dado** uma resposta enviada com fato factual autorizado
- **Quando** o outbound e persistido
- **Entao** `answered_facts` registra o fato com escopo da conversa e versao de conhecimento
- **E** fatos bloqueados por grounding nao sao marcados como respondidos.

#### AC-363 — Avaliacao gratuita nao e repetida em cadastro/agendamento

- **Dado** `answered_facts.evaluation_price=free`
- **Quando** o paciente aceita agendar ou envia dados cadastrais
- **Entao** a resposta operacional nao repete espontaneamente que a avaliacao e gratuita.

#### AC-364 — Interesse em procedimento nao e intencao de agendamento

- **Dado** o paciente pergunta quanto custa a avaliacao ou demonstra interesse em procedimento
- **Quando** ainda nao houve aceite explicito ou contextual ao CTA de agendamento
- **Entao** `appointment_intent=false`.

#### AC-365 — Aceite ao CTA ativa scheduling

- **Dado** a assistente perguntou se o paciente quer ver horario
- **Quando** o paciente responde `sim`, `quero`, `vamos` ou equivalente
- **Entao** `appointment_intent=true`, `next_best_action=SCHEDULE` e o estado entra no fluxo de scheduling.

#### AC-366 — Cadastro nao regride scheduling para discovery

- **Dado** `appointment_intent=true` e o fluxo esta coletando dados
- **Quando** o paciente envia cadastro, unidade, data ou horario
- **Entao** `next_best_action` continua `SCHEDULE` e nao volta para `ASK_DISCOVERY`.

#### AC-367 — Turno cadastral operacional pula RAG

- **Dado** uma mensagem com nome, email, CPF, RG, CEP, endereco, unidade, data ou horario sem pergunta factual
- **Quando** o runtime decide a necessidade de evidencia
- **Entao** registra `TURN_EVIDENCE_REQUIREMENT.reason=OPERATIONAL_NO_RAG`, `retrieval_skipped` e `operational_memory_updated`.

#### AC-368 — Parser cadastral distingue CPF, RG e CEP

- **Dado** a mensagem `Fernando Augusto, fernando@gmail.com, 07693271502, 15125843-02, 17727390, rua praia`
- **Quando** a memoria operacional e atualizada
- **Entao** extrai nome, email, CPF, RG, CEP e rua sem confundir RG com CEP.

#### AC-369 — Pergunta somente campos faltantes

- **Dado** nome, email, CPF, RG, CEP e rua ja conhecidos
- **Quando** ainda faltam numero, bairro, cidade e estado
- **Entao** a resposta pede somente esses campos
- **E** depois de `12, Vilas, Lauro, Bahia`, `registration_complete=true` sem pedir dados ja conhecidos.

#### AC-370 — Endereco nao e inferido por conhecimento externo

- **Dado** o paciente informa `Lauro, Bahia`
- **Quando** o cadastro e atualizado
- **Entao** a cidade permanece `Lauro` e o estado permanece `Bahia`, sem expansao para `Lauro de Freitas`.

#### AC-371 — Dados validos nao criam loop de confirmacao

- **Dado** dados cadastrais validos foram extraidos com confianca suficiente
- **Quando** a resposta operacional e gerada
- **Entao** ela nao pergunta `correto?`, `confirma?` ou confirmacoes equivalentes, salvo ambiguidade, conflito, formato invalido ou acao irreversivel.

### US-096 — Identidade canonica e idempotencia global Z-API

Como operador do sandbox comercial Z-API, quero que telefone canonico e identificadores LID do WhatsApp sejam resolvidos antes de abrir conversa ou executar o runtime, para que uma mesma mensagem/paciente nao gere conversas duplicadas nem respostas duplicadas.

#### AC-373 — Idempotencia global precede conversa e batching

- **Dado** um callback Z-API com `providerAccountId` e `providerMessageId`
- **Quando** o webhook inicia o processamento
- **Entao** a chave `(providerAccountId, providerMessageId)` e verificada antes de resolver `conversationId`, criar lote, executar runtime ou enviar outbound
- **E** uma duplicata e rejeitada com `DUPLICATE_SUPPRESSED`, `provider_message_duplicate_rejected`, zero runtime e zero outbound novo.

#### AC-374 — Telefone e LID do mesmo payload viram identidade canonica

- **Dado** um callback Z-API que exponha telefone e LID do mesmo contato em campos oficiais do provider
- **Quando** a mensagem e normalizada
- **Entao** o adapter registra aliases escopados por `providerAccountId`
- **E** usa um unico `canonicalContactExternalId` para resolver a conversa.

#### AC-375 — Alias LID conhecido reutiliza a conversa canonica

- **Dado** um contato ja visto com telefone e LID associados pelo provider
- **Quando** um callback posterior chega apenas com o LID conhecido
- **Entao** ele resolve para o mesmo `canonicalContactExternalId`, mesmo `conversationId` e historico da conversa original.

#### AC-376 — LIDs distintos nao sao mesclados sem evidencia do provider

- **Dado** dois callbacks com LIDs diferentes e nenhum telefone/alias comum fornecido pelo provider
- **Quando** eles sao processados
- **Entao** o sistema nao faz merge aproximado por texto, nome ou heuristica
- **E** cada LID permanece em conversa propria.

#### AC-377 — Idempotencia nao cruza provider accounts

- **Dado** dois provider accounts diferentes recebem o mesmo `providerMessageId`
- **Quando** os callbacks sao processados
- **Entao** a deduplicacao nao cruza accounts nem organizacoes
- **E** ambos podem gerar seus proprios fluxos isolados.

#### AC-378 — Duplicata dentro de lote nao altera tamanho logico

- **Dado** um lote contem `M1` e `M2`
- **Quando** `M2` chega de novo por outro identificador de contato antes do flush
- **Entao** o lote final contem `providerMessageIds=[M1,M2]`, `message_batch_size=2`, uma unica invocacao do runtime e no maximo um outbound.

#### AC-379 — Unknown instance continua bloqueado

- **Dado** um callback com `instanceId` nao mapeado
- **Quando** a identidade do contato e os aliases estao presentes no payload
- **Entao** a mensagem continua rejeitada como instancia desconhecida
- **E** nenhum alias e persistido para uma organizacao inexistente.

#### AC-380 — Observabilidade de identidade nao expõe dados sensiveis

- **Dado** o processamento Z-API extrai aliases e verifica idempotencia
- **Quando** logs sao emitidos
- **Entao** aparecem `provider_message_idempotency_checked`, `provider_message_duplicate_rejected`, `contact_identifiers_extracted`, `contact_alias_resolved`, `canonical_contact_resolved` e `contact_alias_persisted` quando aplicavel
- **E** os logs nao expoem tokens, secrets nem telefone completo desnecessariamente.

### US-097 — Audio inbound live pelo Z-API

Como paciente no sandbox Z-API, quero enviar audio pelo WhatsApp e receber resposta textual da mesma IA comercial, para validar a conversa real sem criar uma experiencia separada de voz.

#### AC-381 — Audio Z-API e baixado e transcrito antes do runtime

- **Dado** um callback Z-API `AUDIO` com `audio.audioUrl` ou base64, MIME permitido e instancia conhecida
- **Quando** a mensagem e processada
- **Entao** o canal registra `audio_inbound_detected`, baixa a midia com limite seguro, chama `SpeechToTextProvider.transcribe`, preserva transcript/proveniencia e executa o runtime comercial uma unica vez.

#### AC-382 — OpenAI STT usa configuracao existente sem alterar o LLM comercial

- **Dado** `OPENAI_API_KEY` configurada
- **Quando** o servidor live Z-API monta o pipeline de audio
- **Entao** ele usa `OpenAISpeechToTextProvider` com `OPENAI_STT_MODEL`
- **E** o LLM comercial continua usando `OPENAI_RESPONSES_MODEL=gpt-5.6-luna` por padrao.

#### AC-383 — Outbound de audio inbound e sempre texto

- **Dado** uma entrada de audio audivel
- **Quando** o runtime produz resposta
- **Entao** o provider envia somente `send_text`
- **E** nenhum envio de audio, TTS ou voice cloning e acionado.

#### AC-384 — Audio participa do batching multimodal

- **Dado** um audio transcrito e uma mensagem de texto chegam na janela de debounce da mesma conversa
- **Quando** o batch e flushado
- **Entao** ha um unico logical patient turn, com ordem/modalidade preservadas em metadata, uma unica invocacao do runtime e um unico outbound textual.

#### AC-385 — Audio duplicado nao e transcrito duas vezes

- **Dado** o mesmo `providerMessageId` de audio chega por telefone e por LID
- **Quando** a segunda ocorrencia e recebida antes ou depois do flush
- **Entao** a idempotencia `(providerAccountId, providerMessageId)` rejeita a duplicata antes de nova transcricao, batch, runtime ou outbound.

#### AC-386 — Audio inaudivel pede repeticao sem handoff automatico

- **Dado** o STT retorna transcript vazio ou sem fala inteligivel
- **Quando** a midia e processada
- **Entao** a decisao e `MEDIA_RETRY_REQUIRED`
- **E** a resposta textual pede para o paciente reenviar audio ou escrever, sem inventar fato e sem handoff imediato.

#### AC-387 — Falha tecnica de STT recebe retry limitado

- **Dado** a primeira tentativa de transcricao falha por erro tecnico transitorio
- **Quando** uma nova tentativa permitida recupera o transcript
- **Entao** o runtime segue normalmente
- **E** se o retry esgotar, a thread nao morre e o canal produz `MEDIA_RETRY_REQUIRED`.

#### AC-388 — Urgencia clinica transcrita segue a mesma politica do texto

- **Dado** um audio transcrito com sinal clinico de risco como inchaço relevante em implante
- **Quando** o logical turn e processado
- **Entao** a politica atual gera `HUMAN_HANDOFF_REQUIRED` antes de chamada ao modelo quando aplicavel, preservando grounding e sem conduzir clinicamente.

#### AC-389 — Negacao e trecho inaudivel nao viram inferencia insegura

- **Dado** um transcript como `esta inchado mas nao esta sangrando` ou `quanto custa [inaudivel]`
- **Quando** o runtime interpreta o turno
- **Entao** a negacao de sangramento e respeitada
- **E** procedimento inaudivel nao e inferido; a resposta pede esclarecimento textual.

#### AC-390 — Logs de audio sao uteis e seguros

- **Dado** um audio processado pelo Z-API
- **Quando** download, transcricao, retry ou batching ocorrem
- **Entao** aparecem logs como `media_download_started`, `media_download_completed`, `media_download_failed`, `transcription_started`, `transcription_completed`, `transcription_failed`, `transcript_length`, `media_retry_required` e `audio_added_to_batch`
- **E** binario, base64, tokens, URLs assinadas completas e secrets nao sao logados.

### US-098 — Prioridade do turno atual sobre memoria comercial

Como operador do sandbox Z-API, quero que a IA responda primeiro ao que o paciente disse agora, para que memoria comercial antiga ajude a conversa sem sequestrar saudacoes, perguntas simples ou mudancas temporarias de assunto.

#### AC-391 — Saudacao apos contexto comercial antigo nao retoma procedimento

- **Dado** historico persistente com `procedure_interest=lentes`, avaliacao respondida e CTA anterior
- **Quando** o paciente envia apenas uma saudacao apos contexto antigo
- **Entao** `current_turn_intent=GREETING`, `context_continuity=NEW_NEUTRAL_TURN`, `next_best_action=RESPOND_ONLY`
- **E** a resposta nao menciona lentes, avaliacao gratuita, discovery nem agendamento.

#### AC-392 — Pergunta de identidade domina o turno atual

- **Dado** historico comercial ativo ou persistente
- **Quando** o paciente pergunta `Qual seu nome?`
- **Entao** a IA responde somente a identidade configurada
- **E** suprime CTA, procedimento, avaliacao gratuita e proposta de agendamento no mesmo turno.

#### AC-393 — Confirmacao curta logo apos CTA permanece continuacao forte

- **Dado** a assistente acabou de perguntar se deve ver horario
- **Quando** o paciente responde `sim`, `quero` ou equivalente poucos segundos depois
- **Entao** `context_continuity=STRONG_CONTINUATION`
- **E** o fluxo avanca deterministicamente para scheduling sem RAG desnecessario.

#### AC-394 — Continuacao explicita retoma scheduling mesmo apos atraso longo

- **Dado** CTA de agendamento anterior envelhecido
- **Quando** o paciente diz explicitamente `Pode marcar para amanha`
- **Entao** tempo nao reseta sozinho o contexto
- **E** a semantica do turno permite retomar scheduling.

#### AC-395 — Mudanca de topico troca active topic sem misturar procedimentos

- **Dado** memoria persistente com interesse historico em lentes
- **Quando** o paciente pergunta `Vocês fazem implante?`
- **Entao** `active_topic=implante`, `context_continuity=TOPIC_CHANGE`
- **E** a resposta/retrieval nao usa lentes como topico ativo.

#### AC-396 — Side query responde apenas a pergunta lateral

- **Dado** historico persistente com interesse em implante
- **Quando** o paciente pergunta `Qual seu nome?`
- **Entao** `context_continuity=SIDE_QUERY`, `next_best_action=RESPOND_ONLY`
- **E** o historico de implante permanece disponivel, mas nao entra na resposta do turno.

#### AC-397 — Saudacao imediata apos CTA nao e aceite implicito

- **Dado** a assistente acabou de propor agendamento
- **Quando** o paciente responde `Oi`
- **Entao** a saudacao nao e interpretada como aceite do CTA
- **E** nenhum appointment intent, scheduling ou proposta comercial e forçado.

#### AC-398 — Agradecimento encerra naturalmente sem CTA forcado

- **Dado** a assistente respondeu uma pergunta operacional simples
- **Quando** o paciente diz `Obrigado`
- **Entao** a IA responde de forma curta ou encerra naturalmente
- **E** nao adiciona pergunta comercial, discovery ou agendamento.

#### AC-399 — Audio transcrito usa a mesma prioridade do turno atual

- **Dado** um audio transcrito como `qual seu nome?`
- **Quando** o logical turn entra no runtime
- **Entao** a classificacao e as politicas sao identicas ao texto
- **E** nao ha retomada espontanea de procedimento, avaliacao gratuita ou CTA.

#### AC-400 — Avaliacao mede carryover comercial indevido

- **Dado** caso live-like com lentes, avaliacao gratuita, pausa de uma hora, saudacao e pergunta de identidade
- **Quando** a avaliacao executa o dataset comercial
- **Entao** mede `current_turn_intent_accuracy`, `stale_context_reuse_rate`, `inappropriate_context_carryover_rate`, `forced_cta_rate`, `unnecessary_commercial_advance_rate`, `simple_question_overanswer_rate`, `topic_change_accuracy`, `side_query_accuracy`, `pending_cta_resolution_accuracy`, `conversational_naturalness` e `historical_fact_intrusion_rate`
- **E** o caso esperado tem zero mencao espontanea a lentes, avaliacao gratuita, CTA, discovery ou agendamento.

### US-099 — Diagnostico live de retomada neutra e midia Z-API

Como operador do sandbox Z-API, quero que turnos neutros e midias recebidas tenham precedencia e observabilidade reais, para diagnosticar conversas live sem reaproveitar contexto antigo nem perder callbacks silenciosamente.

#### AC-401 — OTHER neutro nao herda contexto comercial stale

- **Dado** memoria persistente com `procedure_interest=lentes`, `answered_facts.evaluation_price=free`, `active_topic=null` e contexto antigo
- **Quando** o paciente envia uma mensagem neutra como `TESTE123`
- **Entao** `context_continuity=NEW_NEUTRAL_TURN`, `next_best_action=RESPOND_ONLY`
- **E** nao ocorre discovery, CTA, scheduling nem retomada de procedimento.

#### AC-402 — Retrieval contextual nao usa historico stale em retomada neutra

- **Dado** o mesmo historico antigo de lentes e avaliacao
- **Quando** o turno atual neutro nao exige evidencia factual
- **Entao** `retrieval_skipped`
- **E** a query contextual, quando registrada para diagnostico, usa apenas o turno atual, sem `lentes`, `avaliacao` ou perguntas antigas.

#### AC-403 — Fato respondido nao reaparece por retrieval stale

- **Dado** `answered_facts.evaluation_price=free`
- **Quando** o turno atual e neutro ou pergunta lateral simples
- **Entao** a resposta nao repete avaliacao gratuita apenas por existir memoria ou evidencia antiga.

#### AC-404 — Idade do contexto usa segundos com unidades explicitas

- **Dado** timestamps numericos em segundos, milissegundos ou ISO
- **Quando** o playbook calcula `context_age_seconds`
- **Entao** os valores de 10 segundos, 5 minutos, 1 hora e 2 horas sao calculados corretamente, sem numeros absurdos.

#### AC-405 — Webhook texto registra ingress seguro antes de normalizar

- **Dado** um callback Z-API oficial de texto
- **Quando** `POST /webhooks/zapi/whatsapp` recebe o payload
- **Entao** registra `zapi_webhook_ingress_received` com metodo, content-type, chaves de topo, instanceId/messageId/type/fromMe e `hasText=true`, sem conteudo completo.

#### AC-406 — Webhook imagem registra ingress mesmo sem processamento posterior

- **Dado** um callback Z-API oficial de imagem
- **Quando** o payload chega ao webhook
- **Entao** registra `zapi_webhook_ingress_received` com `hasImage=true`
- **E** se a imagem for rejeitada depois, existe motivo explicito sem silencio.

#### AC-407 — Webhook audio registra ingress e deteccao de audio

- **Dado** um callback Z-API oficial de audio com `audio.ptt`, `audio.seconds`, `audio.audioUrl`, `audio.mimeType` e `audio.viewOnce`
- **Quando** o payload chega ao webhook
- **Entao** registra `zapi_webhook_ingress_received` com `hasAudio=true`
- **E** registra `audio_inbound_detected` antes de baixar/transcrever.

#### AC-408 — Audio oficial segue ingress, STT e runtime

- **Dado** audio Z-API valido e audivel
- **Quando** o canal processa a midia
- **Entao** o fluxo observado contem ingress, deteccao de audio, download, transcricao e resposta textual, preservando idempotencia e metadata.

#### AC-409 — Midia invalida tem rejeicao explicita

- **Dado** payload de audio, imagem ou documento sem referencia de midia valida
- **Quando** o webhook/canal nao consegue prosseguir
- **Entao** registra motivo como `zapi_media_payload_invalid`, `audio_payload_missing_url`, `zapi_message_type_unsupported` ou `zapi_webhook_rejected`, sem descartar silenciosamente.

#### AC-410 — Regressao de canal permanece protegida

- **Dado** texto, batching, LID, idempotencia, STT e handoff ja implementados
- **Quando** os testes de regressao rodam
- **Entao** esses contratos continuam passando sem alterar debounce, grounding, RAG, Calendar, Meta, Evolution ou CRM.

### US-100 — Servidor Z-API pronto para Render 24/7

Como operador do sandbox comercial, quero rodar o servidor Z-API em um Render Web Service, para receber callbacks reais sem depender do Mac local nem de Cloudflare Tunnel.

#### AC-411 — Server binda em host e porta cloud-ready

- **Dado** um ambiente Render com `PORT`
- **Quando** `python3 -m ai_agent_runtime.whatsapp.zapi_server` inicia
- **Entao** o servidor usa host `0.0.0.0` e a porta de `PORT`.
- **E** sem `PORT`, o fallback local permanece `8082`.

#### AC-412 — Health check local nao depende de servicos externos

- **Dado** o endpoint `GET /health`
- **Quando** Render ou outro monitor consulta o health check
- **Entao** recebe HTTP 200 com payload seguro de status
- **E** a resposta nao chama OpenAI, Supabase, Z-API, Calendar ou LangSmith.

#### AC-413 — Store persistente usa caminho configuravel

- **Dado** `ZAPI_STORE_PATH` configurado para um persistent disk
- **Quando** o servidor sobe e processa mensagens
- **Entao** `JsonFileWhatsAppStore` usa esse caminho, cria diretorios/arquivo quando necessario e preserva dados entre reloads.

#### AC-414 — Producao nao depende de `.sandbox`

- **Dado** `APP_ENV=production` ou ambiente Render sem `ZAPI_STORE_PATH`
- **Quando** o caminho do store e resolvido
- **Entao** o default e `/var/data/zapi-whatsapp-store.json`, nao `.sandbox`.

#### AC-415 — Kill switch desliga runtime e outbound automatico

- **Dado** `AI_INBOUND_ENABLED=false`
- **Quando** um callback Z-API valido chega
- **Entao** o webhook e aceito/controlado, o inbound e registrado para idempotencia, `ai_inbound_disabled` e logado, o runtime nao executa e nenhum outbound automatico e enviado.

#### AC-416 — Kill switch ligado preserva comportamento atual

- **Dado** `AI_INBOUND_ENABLED=true` ou ausente
- **Quando** um callback Z-API valido chega
- **Entao** o fluxo atual de runtime, grounding e outbound permanece ativo.

#### AC-417 — Seguranca existente permanece antes da automacao

- **Dado** `AI_INBOUND_ENABLED=false`
- **Quando** chega payload de instancia desconhecida, duplicado, fora de ordem ou `fromMe`
- **Entao** os guardas existentes continuam valendo e nao sao relaxados pelo kill switch.

#### AC-418 — Render usa start command documentado

- **Dado** a configuracao do Web Service
- **Quando** o operador cria o servico no Render
- **Entao** o start command recomendado e `PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.zapi_server` e o health check path e `/health`.

#### AC-419 — Variaveis de ambiente de deploy nao expoem secrets

- **Dado** `.env.example` e a documentacao Render
- **Quando** alguem consulta a configuracao necessaria
- **Entao** aparecem somente nomes/defaults seguros, sem tokens reais.

#### AC-420 — Regressao de WhatsApp continua protegida

- **Dado** Meta, Evolution, Z-API, batching, audio, RAG, grounding, Calendar e CRM ja especificados
- **Quando** a suite completa roda
- **Entao** o preparo para Render nao altera esses contratos fora do necessario para deploy.

## Fora de escopo

- Definir infraestrutura definitiva/oficial de WhatsApp para producao.
- Remover ou quebrar `MetaWhatsAppCloudProvider`.
- Remover ou quebrar `EvolutionWhatsAppProvider`.
- Criar CRM, campanha, templates promocionais ou automacoes de marketing.
- Usar paciente real ou dados reais de paciente.
- Alterar regras aprovadas de RAG, grounding, Calendar, politica medica ou handoff.
- Gravar tokens ou secrets no repositorio.
- Substituir o runtime real por respostas comerciais hardcoded.
- Responder em audio, implementar TTS, voice cloning ou modo de resposta por voz.

## Suposicoes

| ID | Suposicao | Status | Resolucao |
|---|---|---|---|
| ASM-026 | Z-API sera usada como sessao WhatsApp Web de sandbox/MVP para validacao comercial, nao como infraestrutura definitiva de producao. | confirmada | Definido pelo pedido da feature. |
| ASM-027 | A documentacao consultada nao especifica assinatura HMAC, secret nativo ou header custom verificavel para callbacks `on-message-received`; portanto inbound nao deve depender de `ZAPI_WEBHOOK_SECRET`. | confirmada | Revisado em 2026-08-31: webhook configura apenas URL HTTPS; `Client-Token` e usado nas requisicoes do nosso backend para a API da Z-API. |
| ASM-028 | URLs de midia dos callbacks Z-API sao temporarias e nao devem ser persistidas como autoridade permanente. | confirmada | A documentacao informa disponibilidade de midias por periodo limitado. |
| ASM-029 | `LIVE_VERIFIED` somente sera usado apos chamadas reais opt-in; sem credenciais ou sem flag live, o estado maximo e `READY_FOR_LIVE_EXECUTION`. | confirmada | Mantem seguranca do sandbox e evita falsos positivos. |
| ASM-030 | O historico persistente do Z-API live e um artefato local de sandbox para validacao comercial, nao armazenamento definitivo de producao. | confirmada | O caminho padrao fica em `.sandbox/` e pode ser sobrescrito por `ZAPI_STORE_PATH`. |
| ASM-032 | A melhoria comercial live pode ser feita por guardas deterministicas pequenos e instrucoes de modelo, sem hardcodear uma arvore fixa de vendas. | confirmada | O objetivo e evitar FAQ/enciclopedia e preservar grounding. |
| ASM-034 | Uma claim factual introduzida pelo modelo em turno conversacional pode ser regenerada uma vez em modo `CONVERSATIONAL_NO_FACTS`; se o retry tambem falhar, o caminho seguro e falha interna sem outbound, nao handoff por pedido factual do paciente. | confirmada | Definido para manter grounding forte sem silenciar conversa comercial por erro recuperavel de geracao. |

## Perguntas em aberto

Nenhuma.
