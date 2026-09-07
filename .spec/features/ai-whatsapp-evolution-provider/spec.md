# AI WhatsApp Evolution Provider

> feature: ai-whatsapp-evolution-provider
> status: em-implementacao

## Contexto

Substituir temporariamente a Meta WhatsApp Cloud API pela Evolution API como provider ativo do canal WhatsApp em sandbox, preservando toda a implementacao Meta existente e o contrato abstrato `WhatsAppProvider`.

A Evolution API e usada apenas como provider concreto do canal. O runtime central continua recebendo mensagens normalizadas e nao conhece endpoints, eventos, instancias ou payloads especificos da Evolution.

## Fonte tecnica consultada

Documentacao atual consultada em 2026-08-29:

- Evolution API principal: `https://docs.evolutionfoundation.com.br/evolution-api`
- Envio de texto: `POST /message/sendText/{instanceName}`
- Envio de midia: `POST /message/sendMedia/{instanceName}`
- Criacao de instancia: `POST /instance/create`
- Conexao/QR Code: `GET /instance/connect/{instanceName}`
- Estado de conexao: `GET /instance/connectionState/{instanceName}`
- Webhook por instancia: `POST /webhook/set/{instanceName}`
- Eventos relevantes: `MESSAGES_UPSERT`, `MESSAGES_UPDATE`, `SEND_MESSAGE`, `CONNECTION_UPDATE`, `QRCODE_UPDATED`

Esta feature adota a REST principal `evolution-api`, nao o contrato alternativo `evolution-go`.

## Regras herdadas

Esta feature preserva integralmente:

- `.spec/features/ai-whatsapp-channel/spec.md`
- `.spec/features/ai-agent-runtime/spec.md`
- `.spec/features/ai-runtime-integrations/spec.md`
- `.spec/features/ai-customer-service/spec.md`

Regras inegociaveis:

- `TEXT`, `AUDIO`, `IMAGE` e `DOCUMENT` continuam sendo os tipos suportados pelo canal.
- `organizationId` e resolvido pela instancia/configuracao, nunca pelo conteudo enviado pelo paciente.
- Evento duplicado nao reprocessa runtime nem envia resposta duplicada.
- Self-message nao gera loop.
- Midia e dado, nao instrucao privilegiada.
- Imagem/documento clinico, ambiguo ou nao compreendido exige `HUMAN_HANDOFF_REQUIRED`.
- Grounding, RAG, Calendar e CRM nao sao alterados nesta feature.
- Nenhuma disponibilidade ou fato clinico/comercial pode ser inventado pelo canal.

## Estados

- `IMPLEMENTED`: provider Evolution, webhook, selecao configuravel e testes offline existem.
- `BLOCKED_MISSING_CREDENTIALS`: smoke live foi solicitado sem `EVOLUTION_API_BASE_URL`, `EVOLUTION_API_KEY`, instancia, webhook secret ou URL publica.
- `READY_FOR_LIVE_EXECUTION`: credenciais e URL publica existem, mas ainda nao houve chamada real validada.
- `LIVE_VERIFIED`: reservado para smoke opt-in com chamadas reais a uma instancia Evolution sandbox.

## Historias

### US-050 — Evolution API como provider alternativo

Como operador de sandbox, quero usar Evolution API como provider ativo do WhatsApp, para validar a IA ponta a ponta sem depender da Meta neste momento.

#### AC-156 — Provider Evolution implementa o contrato abstrato

- **Dado** que `WHATSAPP_PROVIDER=evolution`
- **Quando** o provider do canal e construido
- **Entao** ele implementa `WhatsAppProvider`
- **E** o runtime continua sem depender de detalhes da Evolution.

#### AC-157 — Configuracao Evolution vem do ambiente

- **Dado** que o provider Evolution precisa de URL, chave e instancia
- **Quando** a configuracao e carregada
- **Entao** ela usa variaveis de ambiente
- **E** `.env.example` lista os nomes sem valores reais.

#### AC-158 — Selecao de provider preserva Meta

- **Dado** que Meta e Evolution existem no codigo
- **Quando** `WHATSAPP_PROVIDER` e `meta` ou `evolution`
- **Entao** a factory escolhe o provider correspondente
- **E** `MetaWhatsAppCloudProvider` permanece disponivel.

### US-051 — Envio outbound pela Evolution API

Como paciente em sandbox, quero receber resposta pelo WhatsApp conectado na Evolution, para continuar a conversa no mesmo canal.

#### AC-159 — Envio de texto usa endpoint oficial da Evolution

- **Dado** uma resposta textual autorizada pelo runtime
- **Quando** o provider Evolution envia a mensagem
- **Entao** ele chama `POST /message/sendText/{instanceName}` com `apikey`
- **E** envia apenas numero do contato e texto da resposta.

#### AC-160 — Falha da Evolution nao vaza segredo

- **Dado** que a Evolution rejeita a chamada por chave invalida ou indisponibilidade
- **Quando** o erro e propagado
- **Entao** a mensagem tecnica nao contem `EVOLUTION_API_KEY`
- **E** o resultado permanece auditavel.

### US-052 — Webhook Evolution seguro

Como sistema, quero receber eventos Evolution em endpoint proprio, para normalizar mensagens sem expor o runtime ao payload bruto do fornecedor.

#### AC-161 — Webhook Evolution valida segredo quando configurado

- **Dado** um POST em `/webhooks/evolution/whatsapp`
- **Quando** `EVOLUTION_WEBHOOK_SECRET` esta configurado
- **Entao** o endpoint aceita apenas requests com segredo correspondente
- **E** rejeita payload sem autorizacao.

#### AC-162 — Parser normaliza texto e midias

- **Dado** eventos `MESSAGES_UPSERT` com texto, audio, imagem ou documento
- **Quando** o parser Evolution processa o payload
- **Entao** ele produz eventos internos com `providerAccountId`, `providerMessageId`, `contactExternalId`, tipo, texto, MIME, filename e referencia de midia.

#### AC-163 — Instancia desconhecida e bloqueada

- **Dado** um webhook de instancia nao registrada
- **Quando** o adapter tenta resolver a organizacao
- **Entao** a mensagem e rejeitada antes do runtime
- **E** nenhum `organizationId` do payload e usado como fonte de verdade.

#### AC-164 — Duplicacao, ordem e self-message continuam protegidos

- **Dado** eventos Evolution duplicados, fora de ordem ou enviados pela propria instancia
- **Quando** chegam ao canal
- **Entao** a idempotencia por message id, historico por conversa e self-message protection continuam iguais ao contrato base.

### US-053 — Midia Evolution segue politica existente

Como paciente em sandbox, quero enviar audio, imagem ou documento pelo WhatsApp, para que o canal processe o material sem enfraquecer seguranca medica.

#### AC-165 — Download de midia usa fonte segura do evento

- **Dado** uma midia recebida pela Evolution
- **Quando** o canal precisa dos bytes
- **Entao** ele usa `base64` recebido no webhook ou `mediaUrl` autenticavel
- **E** nao trata URL temporaria como referencia permanente.

#### AC-166 — Audio Evolution segue STT e retry seguro

- **Dado** uma mensagem `AUDIO`
- **Quando** a midia e baixada, validada e transcrita
- **Entao** o transcript segue para o runtime
- **E** audio inaudivel gera `MEDIA_RETRY_REQUIRED` sem inventar conteudo.

#### AC-167 — Imagem Evolution preserva handoff clinico

- **Dado** uma mensagem `IMAGE`
- **Quando** o conteudo e clinico, ambiguo ou nao compreendido
- **Entao** o canal produz `HUMAN_HANDOFF_REQUIRED`
- **E** nao envia interpretacao clinica ao paciente.

#### AC-168 — Documento Evolution preserva filename, MIME e texto extraido

- **Dado** uma mensagem `DOCUMENT`
- **Quando** o canal processa o arquivo
- **Entao** preserva provider media id, filename, MIME, referencia/storage e texto extraido quando permitido
- **E** documentos clinicos ou nao compreendidos geram handoff.

### US-054 — Operacao de instancia sandbox

Como operador tecnico, quero comandos claros para instancia Evolution, QR Code, webhook e smoke, para executar o primeiro teste real sem misturar dados reais.

#### AC-169 — Provider consulta estado de conexao

- **Dado** uma instancia Evolution configurada
- **Quando** o status e consultado
- **Entao** o provider chama `GET /instance/connectionState/{instanceName}`
- **E** retorna estado sem logar a chave.

#### AC-170 — Provider cria instancia e obtem QR Code quando solicitado

- **Dado** que a instancia sandbox ainda precisa ser conectada
- **Quando** comandos administrativos opt-in sao executados
- **Entao** a Evolution recebe `POST /instance/create` ou `GET /instance/connect/{instanceName}`
- **E** qualquer QR Code retorna apenas como dado operacional de sandbox.

#### AC-171 — Provider registra webhook por instancia

- **Dado** uma URL publica de sandbox
- **Quando** o webhook e configurado
- **Entao** o provider chama `POST /webhook/set/{instanceName}`
- **E** assina/identifica requests com segredo configurado.

#### AC-172 — Smoke Evolution bloqueia sem credenciais

- **Dado** que o smoke live e solicitado sem configuracao completa
- **Quando** o comando roda
- **Entao** o resultado e `BLOCKED_MISSING_CREDENTIALS`
- **E** apenas nomes de variaveis faltantes sao impressos.

#### AC-173 — Smoke Evolution planeja cenarios live

- **Dado** que credenciais e URL publica existem
- **Quando** o smoke live e preparado
- **Entao** ele lista inbound text, outbound text, audio, image, document, duplicado, self-message, handoff, scheduling, connection state, QR/connect e webhook setup
- **E** nao marca `LIVE_VERIFIED` sem chamadas reais a Evolution.

### US-055 — Compatibilidade e observabilidade

Como responsavel tecnico, quero preservar rastreabilidade e compatibilidade, para trocar providers sem regressao nos contratos existentes.

#### AC-174 — Logs/auditoria redigem credenciais

- **Dado** payloads, respostas e erros Evolution
- **Quando** sao reportados em smoke ou excecoes
- **Entao** API key, webhook secret e tokens nao aparecem em logs.

#### AC-175 — Meta nao sofre regressao

- **Dado** que a implementacao Meta existente permanece no projeto
- **Quando** os testes do canal rodam
- **Entao** os testes Meta continuam passando.

#### AC-176 — Evolution nao altera CRM, RAG, Calendar ou grounding

- **Dado** a integracao Evolution implementada
- **Quando** os arquivos alterados sao inspecionados
- **Entao** nao ha mudanca de contrato funcional em CRM, RAG, Calendar ou grounding
- **E** o canal continua delegando decisao ao runtime.

## Fora de escopo

- Remover ou depreciar `MetaWhatsAppCloudProvider`.
- Integrar CRM ou Central de Atendimento.
- Alterar regras de RAG, Calendar, grounding, handoff ou politica medica.
- Usar paciente real.
- Subir infraestrutura externa automaticamente.
- Comitar `.env`, tokens, API keys, QR Codes persistentes ou sessoes WhatsApp.

## Suposições

| ID | Suposição | Status | Resolução |
|---|---|---|---|
| ASM-023 | A primeira implementacao deve mirar a REST principal `evolution-api`, nao `evolution-go`, porque os endpoints documentados de provider existente usam `/message/sendText/{instanceName}`, `/message/sendMedia/{instanceName}` e `/webhook/set/{instanceName}`. | confirmada | Definido a partir da documentacao atual consultada em 2026-08-29. |
| ASM-024 | A validacao de webhook pode usar segredo compartilhado em header configurado no webhook da instancia, porque a documentacao permite `headers` no `/webhook/set/{instanceName}` e nao define assinatura HMAC obrigatoria unica. | confirmada | Implementar header proprio de sandbox sem enfraquecer autenticacao. |
| ASM-025 | O smoke live pode ficar `READY_FOR_LIVE_EXECUTION` sem executar chamada real quando `RUN_EVOLUTION_LIVE` nao estiver ativo, mantendo a suite offline independente de Evolution. | confirmada | Coerente com o padrao existente de live sandbox opt-in. |

## Perguntas em aberto

Nenhuma.
