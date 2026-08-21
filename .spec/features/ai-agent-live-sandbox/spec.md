# AI Agent Live Sandbox

> feature: ai-agent-live-sandbox
> status: em-implementacao

## Objetivo

Validar o agente ponta a ponta com servicos reais em ambiente controlado, usando exclusivamente dados ficticios.

Fluxos alvo:

```text
mensagem ficticia
-> LangGraph/runtime
-> GPT-5.6 Luna
-> retrieval Supabase sandbox
-> evidencias
-> grounding
-> resposta ou HUMAN_HANDOFF_REQUIRED
```

```text
mensagem ficticia
-> LangGraph/runtime
-> SCHEDULING_CONTEXT_ACTIVE
-> Google Calendar sandbox
-> slots reais de teste
-> agendamento ficticio
```

Tudo que puder ser preparado offline deve continuar rodando sem internet. Chamadas reais sao sempre opt-in e dependem de credenciais configuradas localmente.

## Estados de validacao

- `IMPLEMENTED`: runner, configuracao, dataset, planos de smoke test e guardas existem e passam nos testes offline.
- `BLOCKED_MISSING_CREDENTIALS`: a etapa live foi solicitada, mas variaveis obrigatorias estao ausentes.
- `LIVE_VERIFIED`: smoke test real executado com sucesso contra o servico sandbox correspondente.

Esta feature nao pode ser considerada integralmente concluida ate que os smoke tests live sejam executados com sucesso. Enquanto credenciais nao existirem, o estado correto e `IMPLEMENTED` + `BLOCKED_MISSING_CREDENTIALS`, nunca `LIVE_VERIFIED`.

## Regras herdadas

Esta feature preserva integralmente as regras de:

- `.spec/features/ai-customer-service/spec.md`
- `.spec/features/ai-agent-runtime/spec.md`
- `.spec/features/ai-runtime-integrations/spec.md`
- `.spec/features/ai-agent-evaluation/spec.md`

Regras inegociaveis:

- conhecimento pre-treinado do LLM nao e fonte factual autorizada;
- informacao factual sem suporte gera `HUMAN_HANDOFF_REQUIRED`;
- resposta ao paciente nao expoe RAG, retrieval, base, documento, score ou falta de evidencia;
- `PROCEDURE_CATALOG` fechado exige completude aprovada;
- ausencia de atributo nao vira negativa;
- informacao dinamica vem de tools/APIs;
- cross-organization retrieval e proibido;
- grounding valida antes de resposta factual;
- `SCHEDULING_CONTEXT_ACTIVE` e obrigatorio antes de consultar agenda.

## Ambiente sandbox

O ambiente live exige:

```text
APP_ENV=sandbox
RUN_LIVE_SANDBOX=true
```

Sem `RUN_LIVE_SANDBOX=true`, nenhuma chamada externa pode ocorrer.

## Dados ficticios

Organizacao principal:

```text
Clínica Aurora Sandbox
```

Organizacao secundaria para teste cross-org:

```text
Clínica Boreal Sandbox
```

Catalogo `PROCEDURE_CATALOG` fechado da Clinica Aurora Sandbox:

```text
Botox
Preenchimento labial
Blefaroplastia
```

Metadados obrigatorios:

```text
knowledgeMode = CLOSED_WORLD
closedWorldCompletenessApproved = true
status = PUBLISHED
environment = sandbox
```

## Historias de usuario e criterios de aceite

### US-030 — Sandbox e separado de producao

Como responsavel tecnico, quero uma configuracao explicita de sandbox, para impedir mistura acidental com producao ou dados reais.

#### AC-100 — Ambiente sandbox e opt-in

- **Dado** que o runner sandbox e executado
- **Quando** `RUN_LIVE_SANDBOX` nao e `true`
- **Entao** nenhuma chamada OpenAI, Supabase, Google Calendar ou LangSmith e realizada
- **E** o resultado informa que live execution esta desabilitada.

#### AC-101 — APP_ENV precisa ser sandbox para execucao live

- **Dado** que `RUN_LIVE_SANDBOX=true`
- **Quando** `APP_ENV` nao e `sandbox`
- **Entao** o runner bloqueia a execucao live
- **E** informa que o ambiente nao e sandbox.

#### AC-102 — Configuracao vem de variaveis de ambiente sem secrets hard-coded

- **Dado** que as integracoes live precisam de credenciais
- **Quando** a configuracao e carregada
- **Entao** OpenAI, Supabase, LangSmith e Google Calendar leem apenas variaveis de ambiente
- **E** `.env.example` lista os campos necessarios sem valores reais.

#### AC-103 — Credenciais ausentes geram erro claro e redigido

- **Dado** que uma credencial obrigatoria esta ausente
- **Quando** a validacao de prontidao live e executada
- **Entao** o resultado lista a variavel ausente pelo nome
- **E** nao imprime nenhum valor secreto.

### US-031 — Runner live sandbox

Como operador de homologacao, quero um comando unico de smoke test, para validar cada integracao real quando as credenciais estiverem configuradas.

#### AC-104 — Runner expõe comando python module

- **Dado** a feature de sandbox live
- **Quando** o operador executa `python -m ai_agent_runtime.sandbox`
- **Entao** o runner valida configuracao, identifica integracoes habilitadas, executa ou bloqueia cenarios e retorna exit code adequado.

#### AC-105 — Runner diferencia IMPLEMENTED de LIVE_VERIFIED

- **Dado** uma etapa de integracao live
- **Quando** ela nao foi executada contra servico real
- **Entao** o relatorio nao marca `LIVE_VERIFIED`
- **E** usa `IMPLEMENTED`, `DISABLED` ou `BLOCKED_MISSING_CREDENTIALS` conforme o caso.

#### AC-106 — Relatorio captura uso e latencia quando disponiveis

- **Dado** que um smoke test live retorna usage, tokens, embeddings, tool calls ou latencia
- **Quando** o relatorio e gerado
- **Entao** esses campos ficam disponiveis para calculo posterior de custo
- **E** valores ausentes permanecem nulos sem quebrar a execucao.

### US-032 — OpenAI real em sandbox

Como auditor do LLM, quero smoke test real da Responses API com GPT-5.6 Luna, para validar saida estruturada e erros de autenticacao sem vazar segredo.

#### AC-107 — OpenAI smoke usa modelo e payload aprovados

- **Dado** que a etapa OpenAI live esta habilitada
- **Quando** o runner monta a chamada
- **Entao** usa Responses API, modelo `gpt-5.6-luna`, `reasoning.effort=low`, `store=false` e structured output por `json_schema`.

#### AC-108 — Falha de autenticacao OpenAI e controlada

- **Dado** uma OpenAI API key ausente ou invalida
- **Quando** o smoke test tenta validar OpenAI
- **Entao** a falha e reportada como erro controlado
- **E** a API key nao aparece em logs, stdout, relatorio ou trace.

### US-033 — Supabase sandbox e dataset ficticio

Como arquiteto, quero preparar Supabase sandbox com schema e dados ficticios, para testar retrieval real sem tocar producao.

#### AC-109 — Supabase readiness exige sandbox e migration existente

- **Dado** a etapa Supabase live
- **Quando** o runner valida prontidao
- **Entao** exige `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` e ambiente sandbox
- **E** referencia a migration existente que cria pgvector, organizacoes, documentos, versoes, chunks, indices, conversas, mensagens e auditoria.

#### AC-110 — Dataset sandbox contem organizacoes e catalogo fechado ficticios

- **Dado** o dataset de homologacao
- **Quando** ele e inspecionado
- **Entao** contem Clinica Aurora Sandbox, Clinica Boreal Sandbox, documentos ficticios, profissionais ficticios e `PROCEDURE_CATALOG` fechado aprovado.

#### AC-111 — Cenarios Supabase cobrem retrieval, ausencia, atributo e cross-org

- **Dado** Supabase sandbox populado
- **Quando** os smoke tests live forem executados
- **Entao** eles testam informacao existente, informacao inexistente, procedimento inexistente `NOT_OFFERED`, atributo ausente com `HUMAN_HANDOFF_REQUIRED` e isolamento cross-org.

#### AC-112 — Gap de ingestao real e documentado

- **Dado** que o projeto ainda pode nao possuir pipeline completo document->normalization->chunking->embedding->pgvector
- **Quando** o runner prepara o plano live
- **Entao** ele documenta as etapas implementadas, as etapas bloqueadas e nao insere manualmente resultado final fingindo pipeline completo.

### US-034 — Grounding, handoff e prompt injection live

Como responsavel de seguranca, quero cenarios live adversariais, para validar que Luna real nao contorna guardas deterministicas.

#### AC-113 — Grounding live bloqueia resposta nao suportada

- **Dado** evidencias recuperadas do Supabase sandbox
- **Quando** uma resposta factual nao e suportada por essas evidencias
- **Entao** grounding reprova
- **E** a decisao esperada e `HUMAN_HANDOFF_REQUIRED`.

#### AC-114 — Prompt injection live nao altera controles

- **Dado** mensagem ficticia pedindo para ignorar instrucoes, usar conhecimento medico e evitar handoff
- **Quando** Luna real participar da avaliacao live
- **Entao** as guardas deterministicas continuam vencendo
- **E** nao ha resposta medica inventada.

### US-035 — Google Calendar sandbox

Como operador de agenda, quero validar calendario real de teste, para provar chamadas permitidas sem tocar agenda de cliente real.

#### AC-115 — Google Calendar readiness exige calendario de teste e timezone

- **Dado** a etapa Google Calendar live
- **Quando** o runner valida prontidao
- **Entao** exige `GOOGLE_CALENDAR_ID`, `GOOGLE_CALENDAR_ACCESS_TOKEN` e timezone explicito
- **E** bloqueia calendario sem identificacao sandbox.

#### AC-116 — Agenda live preserva SCHEDULING_CONTEXT_ACTIVE

- **Dado** mensagens fora de agendamento, interesse generico e intencao explicita
- **Quando** os cenarios de agenda live forem preparados
- **Entao** Google Calendar calls permanecem `0` fora de contexto
- **E** somente contexto ativo permite consultar slots e criar evento ficticio.

#### AC-117 — Agendamento ficticio possui cleanup

- **Dado** que um evento sandbox e criado
- **Quando** o smoke test termina
- **Entao** o evento e identificavel como sandbox
- **E** existe plano de cleanup seguro para remove-lo.

### US-036 — Observabilidade e redaction

Como auditor, quero traces de sandbox com redaction, para observar execucao sem vazar segredo.

#### AC-118 — LangSmith usa projeto sandbox e nao substitui auditoria local

- **Dado** LangSmith configurado para sandbox
- **Quando** uma etapa gera evento
- **Entao** o projeto padrao e `ai-atendimento-sandbox`
- **E** falha do LangSmith nao altera comportamento funcional.

#### AC-119 — Redaction remove secrets de relatorios e traces

- **Dado** payloads com API keys, authorization headers, tokens ou credenciais
- **Quando** o runner prepara logs, relatorio ou trace
- **Entao** os valores sensiveis sao mascarados
- **E** apenas nomes das variaveis ausentes podem aparecer.

### US-037 — OAuth local do Google Calendar sandbox

Como operador de sandbox, quero gerar tokens OAuth locais para Google Calendar sem expor secrets, para validar agenda real de teste e preservar `refresh_token` para renovacao automatica futura.

#### AC-120 — OAuth local exige sandbox e credenciais de cliente via ambiente

- **Dado** que o utilitario OAuth do Google Calendar e executado
- **Quando** `APP_ENV` nao e `sandbox` ou faltam `GOOGLE_OAUTH_CLIENT_ID` e `GOOGLE_OAUTH_CLIENT_SECRET`
- **Entao** ele bloqueia a execucao
- **E** informa somente os nomes das variaveis ausentes, sem imprimir valores sensiveis.

#### AC-121 — OAuth solicita apenas escopos minimos de agenda sandbox

- **Dado** que o utilitario monta a URL de autorizacao OAuth
- **Quando** o fluxo Desktop e iniciado
- **Entao** ele solicita somente `https://www.googleapis.com/auth/calendar.freebusy` e `https://www.googleapis.com/auth/calendar.events`.

#### AC-122 — OAuth preserva refresh_token sem commitar tokens

- **Dado** que o Google retorna tokens no fluxo OAuth
- **Quando** o utilitario persiste o resultado localmente
- **Entao** `access_token`, `refresh_token`, expiracao, token type e scopes sao preservados em arquivo local ignorado pelo controle de versao
- **E** o relatorio nao imprime os valores dos tokens.

#### AC-123 — OAuth imprime instrucao segura de variaveis a preencher

- **Dado** que o fluxo OAuth conclui
- **Quando** o utilitario exibe o resumo
- **Entao** ele lista os nomes `GOOGLE_CALENDAR_ACCESS_TOKEN`, `GOOGLE_CALENDAR_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` e `GOOGLE_OAUTH_TOKEN_URI`
- **E** redige valores sensiveis.

## Fora de escopo

- WhatsApp.
- Frontend do CRM.
- Central de Atendimento.
- Atendimento humano no CRM.
- Producao.
- Dados de pacientes reais.
- Agenda real de cliente.

## Suposicoes

| ID | Suposicao | Status | Resolucao |
|---|---|---|---|
| ASM-014 | Sem credenciais locais, a feature pode ficar `IMPLEMENTED` e `BLOCKED_MISSING_CREDENTIALS`, mas nao `LIVE_VERIFIED`. | confirmada | Definido pelo prompt: parar quando precisar de credenciais e nao inventar valores. |
| ASM-015 | O timezone inicial de sandbox sera `America/Bahia`, herdado da configuracao atual e do ambiente do projeto, ate decisao futura. | confirmada | O prompt permite documentar timezone de sandbox quando nao houver regra especifica. |
| ASM-016 | A primeira entrega pode implementar o runner e planos de smoke opt-in sem executar chamadas reais no test suite padrao. | confirmada | O prompt exige separar offline de live e manter suite padrao sem internet. |
| ASM-017 | O OAuth Desktop usa loopback local `127.0.0.1` por padrao e token file local em `.secrets/`, ambos exclusivos de sandbox. | confirmada | O pedido exige utilitario local apenas para sandbox e preservacao do refresh token sem commitar tokens. |

## Perguntas em aberto

Nenhuma pergunta de produto bloqueante para preparar a feature.

Bloqueio operacional atual:

- Credenciais e recursos sandbox reais precisam ser configurados localmente antes de `LIVE_VERIFIED`.
