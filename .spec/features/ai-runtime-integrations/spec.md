# AI Runtime Integrations

> feature: ai-runtime-integrations
> status: em-implementacao

## Objetivo

Integrar o runtime concluido em `ai-agent-runtime` aos primeiros servicos reais necessarios para a IA de atendimento funcionar fora de providers in-memory, preservando as regras de `ai-customer-service`.

## Stack aprovada

- Python
- LangGraph
- OpenAI Responses API
- GPT-5.6 Luna como LLM principal
- Supabase / PostgreSQL
- pgvector
- LangSmith
- Google Calendar como primeiro `CalendarProvider`

## Fora do escopo atual

Nao integrar ainda WhatsApp, frontend do CRM, Central de Atendimento, handoff visual do CRM ou integracao completa com CRM.

## Regras herdadas

- `SCHEDULING_CONTEXT_ACTIVE` continua obrigatorio antes de consultar agenda.
- `organizationId` continua obrigatorio em retrieval, persistencia e auditoria.
- Conhecimento documental nao se mistura com memoria individual de paciente.
- Embedding, score ou pgvector nao autorizam resposta.
- Versoes nao publicadas, expiradas, invalidas ou cross-org nao podem fundamentar resposta.
- Grounding validator continua sendo o gate antes de resposta factual.
- LangSmith nao substitui auditoria de negocio.

## Decisoes tecnicas desta feature

- Modelo LLM principal: `gpt-5.6-luna`.
- Reasoning effort inicial: `low`, para baixa latencia.
- Modelo de embedding MVP: `text-embedding-3-small`, escolhido por custo/qualidade adequada para MVP e reversibilidade tecnica.
- Testes padrao usam fakes/transports locais; nao dependem de internet nem credenciais.

## Historias de usuario e criterios de aceite

### US-015 — Configuracao segura de integracoes

Como operador do sistema, quero configurar OpenAI, Supabase, LangSmith e Google por ambiente, para nao colocar segredos no codigo.

#### AC-049 — Configuracao vem de ambiente

- **Dado** que uma integracao precisa de credenciais
- **Quando** o provider e construido
- **Entao** ele le credenciais de variaveis de ambiente ou objeto de configuracao
- **E** nao possui segredo hard-coded.

#### AC-050 — Exemplo de ambiente nao contem segredos reais

- **Dado** que o repositorio documenta variaveis necessarias
- **Quando** `.env.example` e inspecionado
- **Entao** ele lista as variaveis sem valores reais de segredo.

### US-016 — Supabase/PostgreSQL persiste conhecimento e runtime

Como arquiteto, quero schema real planejado em Supabase/PostgreSQL, para persistir documentos, chunks, conversas e auditoria com isolamento por organizacao.

#### AC-051 — Migration habilita pgvector e entidades documentais

- **Dado** que o schema e aplicado
- **Quando** a migration e inspecionada
- **Entao** ela habilita `vector`
- **E** cria tabelas para organizacoes, documentos, versoes, chunks, indices, conversas, mensagens e auditoria.

#### AC-052 — Constraints preservam organizationId

- **Dado** que entidades documentais e conversacionais sao persistidas
- **Quando** a migration define relacionamentos
- **Entao** `organization_id` e obrigatorio
- **E** relacoes cross-org sao prevenidas por chaves compostas ou constraints equivalentes.

#### AC-053 — Knowledge base nao armazena memoria individual de paciente

- **Dado** que o schema documental e criado
- **Quando** tabelas de conhecimento sao inspecionadas
- **Entao** documentos, versoes, chunks e indices nao possuem `patient_id`.

### US-017 — Retrieval real usa lexical + vector com elegibilidade

Como paciente, quero respostas factuais baseadas apenas em evidencias elegiveis, para evitar uso de conteudo nao publicado ou de outra organizacao.

#### AC-054 — Retrieval rejeita organizationId ausente ou cross-org

- **Dado** que uma busca documental e solicitada
- **Quando** `organizationId` esta ausente ou um candidato pertence a outra organizacao
- **Entao** o provider rejeita a operacao ou remove o candidato.

#### AC-055 — Versao nao publicada ou expirada nao e recuperavel

- **Dado** que candidatos possuem metadados de versao
- **Quando** uma versao nao esta `PUBLISHED`, esta invalida ou fora de vigencia
- **Entao** ela nao participa das evidencias.

#### AC-056 — Hybrid retrieval combina lexical e vetorial sem autorizar por score

- **Dado** que lexical e vector retornam candidatos
- **Quando** o provider funde resultados
- **Entao** ele preserva metadados, origem, score e versao
- **E** marca que grounding ainda e obrigatorio.

### US-018 — OpenAI provider usa Responses API com saida estruturada

Como runtime, quero chamar OpenAI por provider, para obter classificacoes, tool routing ou claims estruturados sem parsing fragil.

#### AC-057 — Provider OpenAI usa Responses API e modelo aprovado

- **Dado** que o LLM provider e chamado
- **Quando** ele monta a requisicao
- **Entao** usa endpoint de Responses API
- **E** modelo `gpt-5.6-luna`.

#### AC-058 — Provider usa reasoning low para baixa latencia

- **Dado** que a configuracao padrao e usada
- **Quando** a requisicao OpenAI e montada
- **Entao** `reasoning.effort` e `low`.

#### AC-059 — Structured outputs usam json_schema

- **Dado** que uma decisao estruturada e solicitada
- **Quando** o provider recebe schema
- **Entao** envia `text.format.type = json_schema`
- **E** nao depende de parsing livre.

#### AC-060 — Falha do LLM retorna erro controlado

- **Dado** que a Responses API falha
- **Quando** o provider recebe erro ou resposta falha
- **Entao** retorna excecao controlada para o runtime transformar em handoff/erro auditavel.

### US-019 — Embeddings OpenAI sao rastreaveis

Como operador de RAG, quero embeddings com modelo e versao rastreaveis, para auditar indices e reindexacoes.

#### AC-061 — Embedding registra modelo, versao e indexedAt

- **Dado** que um texto e enviado para embedding
- **Quando** o provider retorna vetor
- **Entao** o resultado inclui modelo, versao e `indexedAt`.

### US-020 — LangSmith observa sem substituir auditoria

Como auditor, quero observabilidade externa com protecao de dados, sem depender dela para auditoria de negocio.

#### AC-062 — LangSmith observer aplica redaction razoavel

- **Dado** que um evento contem telefone, email ou texto sensivel
- **Quando** o observer prepara payload
- **Entao** aplica redaction antes de enviar ao LangSmith.

#### AC-063 — Falha do LangSmith nao altera comportamento do dominio

- **Dado** que LangSmith esta indisponivel
- **Quando** o runtime registra evento
- **Entao** auditoria local continua funcionando
- **E** a excecao externa nao interrompe o fluxo.

### US-021 — Google Calendar implementa CalendarProvider

Como runtime de agenda, quero usar Google Calendar atras da interface `CalendarProvider`, para consultar e alterar agenda sem acoplar o agente ao fornecedor.

#### AC-064 — Google Calendar implementa operacoes do provider

- **Dado** que o provider real de calendario e criado
- **Quando** sua interface e inspecionada
- **Entao** ele suporta consultar disponibilidade, criar, reagendar e cancelar agendamento.

#### AC-065 — Guarda bloqueia Google Calendar fora do contexto

- **Dado** que o LLM tenta consultar disponibilidade
- **Quando** `SCHEDULING_CONTEXT_ACTIVE` nao esta ativo
- **Entao** a guarda deterministica bloqueia antes de qualquer chamada Google.

#### AC-066 — Slots apresentados vêm do Google Calendar provider

- **Dado** que disponibilidade sera apresentada
- **Quando** a tool retorna slots
- **Entao** os slots correspondem exatamente ao retorno valido do provider
- **E** o LLM nao inventa datas ou horarios.

## Suposicoes

| ID | Suposicao | Status |
|---|---|---|
| ASM-009 | Providers reais podem ser implementados com transports injetaveis para testes unitarios offline. | confirmada |
| ASM-010 | A migration SQL e suficiente para definir o schema inicial sem aplicar em um Supabase real nesta tarefa. | confirmada |
| ASM-011 | `text-embedding-3-small` atende o MVP por custo/qualidade e pode ser trocado por reindexacao futura. | confirmada |

## Perguntas em aberto

Nenhuma pergunta bloqueante para a implementacao isolada desta feature.

Decisoes que exigirao credenciais ou produto futuro:

- valores reais de `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `LANGSMITH_API_KEY` e credenciais Google;
- calendario real, duracao padrao, buffers, medicos, unidades e regras comerciais de bloqueio;
- schema definitivo de CRM e Central de Atendimento.
