# AI Agent Runtime

> feature: ai-agent-runtime
> status: em-implementacao

## Objetivo

Implementar o runtime real do agente de atendimento comercial, em Python, com LangGraph como orquestrador aprovado, reutilizando as regras e fundacoes da feature `ai-customer-service`.

Esta feature nao redefine as regras de produto. Ela operacionaliza os contratos ja aprovados em:

- `.spec/features/ai-customer-service/spec.md`
- `.spec/features/ai-customer-service/product-rules.md`
- `.spec/features/ai-customer-service/rag-contract.md`
- `.spec/features/ai-customer-service/ingestion-contract.md`
- `.spec/features/ai-customer-service/data-model.md`
- `.spec/features/ai-customer-service/chunking-contract.md`

## Stack aprovada

- Python
- LangGraph
- Supabase / PostgreSQL
- pgvector
- retrieval hibrido lexical + vetorial
- LangSmith para observabilidade do agente
- integracoes externas por interfaces/providers
- WhatsApp posteriormente como canal de entrada/saida

## Arquitetura conceitual

```text
Mensagem
↓
AgentState
↓
LangGraph / runtime graph
↓
Interpretacao da mensagem
↓
Intencao + estagio conversacional
↓
Decisao
├── pergunta factual → retrieval hibrido isolado por organizationId → grounding
├── dado dinamico/acao → tool permitida via provider
├── agendamento ativo → calendar tools guardadas
└── informacao sem suporte → HUMAN_HANDOFF_REQUIRED
↓
Auditoria operacional + observabilidade
↓
Resposta / handoff / tool result
```

## Regras herdadas de `ai-customer-service`

O runtime deve respeitar integralmente:

- conhecimento pre-treinado do LLM nao e fonte factual autorizada sobre a clinica;
- informacao factual sem suporte autorizado resulta em `HUMAN_HANDOFF_REQUIRED`;
- resposta final ao paciente nao expoe RAG, retrieval, base, documentos, score, falha de busca ou ausencia de evidencia;
- ausencia so sustenta negativa em fonte `CLOSED_WORLD` aprovada no escopo certo;
- `PROCEDURE_CATALOG` fechado usa consulta deterministica, nao ausencia vetorial;
- ausencia de atributo nao significa negativa;
- informacao dinamica deve vir de tools/APIs autorizadas;
- cross-organization retrieval e proibido;
- chunks nao possuem autoridade independente da versao documental;
- grounding valida antes de resposta factual.

## Agendamento

A agenda nao deve ser consultada em toda conversa.

O runtime deve possuir estado ou condicao equivalente a:

```text
SCHEDULING_CONTEXT_ACTIVE
```

`get_availability()` so pode ser chamado quando:

- o estagio conversacional esta em contexto de agendamento; e
- a intencao atual exige disponibilidade real.

Interesse comercial generico nao autoriza consulta de agenda.

## Providers

O agente nao deve conhecer fornecedores externos diretamente. As integracoes ficam atras de interfaces:

```python
class CalendarProvider:
    def get_availability(...)
    def create_appointment(...)
    def reschedule_appointment(...)
    def cancel_appointment(...)

class CRMProvider:
    def upsert_contact(...)
    def update_stage(...)
    def update_fields(...)
    def add_note(...)
```

Supabase/PostgreSQL/pgvector e a infraestrutura planejada para dados documentais, indices, metadados e auditoria operacional, mas credenciais e schema fisico nao sao definidos nesta feature.

## CRM

O runtime pode atualizar CRM progressivamente com informacoes confiaveis surgidas na conversa.

Nao deve inventar dados para completar cadastro. Campos ausentes permanecem ausentes.

## Observabilidade e auditoria

LangSmith pode rastrear execucao do graph, nodes, modelo, latencia, retrieval, tool calls, erros, grounding e handoffs.

LangSmith nao e a unica fonte de auditoria de negocio. O dominio proprio deve persistir eventos criticos equivalentes a:

- `conversationId`
- `organizationId`
- `intent`
- `decision`
- `toolCalled`
- `documentVersionsUsed`
- `groundingResult`
- `handoffReason`
- timestamps

## Escopo atual

Implementar fundacoes testaveis e isoladas do runtime. Nao implementar WhatsApp nesta feature. Nao escolher fornecedor real de agenda, CRM, LLM ou Supabase sem necessidade tecnica e credenciais.

## Historias de usuario e criterios de aceite

### US-008 — Runtime mantem estado conversacional

Como agente de atendimento, quero manter estado de conversa, intencao e estagio, para decidir corretamente entre resposta, tool e handoff.

#### AC-033 — Estado registra organizacao e conversa

- **Dado** que uma mensagem chega ao runtime
- **Quando** o estado da conversa e criado ou atualizado
- **Entao** ele preserva `conversationId`, `organizationId`, mensagem atual, intencao atual e estagio conversacional.

#### AC-034 — Runtime decide handoff quando regra herdada exige

- **Dado** que uma decisao de dominio retorna `HUMAN_HANDOFF_REQUIRED`
- **Quando** o graph processa a mensagem
- **Entao** o runtime interrompe o fluxo autonomo normal
- **E** prepara handoff com contexto suficiente.

### US-009 — Agenda so e consultada em contexto de agendamento

Como administrador da clinica, quero que disponibilidade seja consultada apenas quando o paciente quer agendar, para evitar chamadas indevidas e comportamento invasivo.

#### AC-035 — Interesse geral nao ativa agenda

- **Dado** que o paciente demonstrou interesse comercial geral
- **Quando** a mensagem nao pede disponibilidade nem confirma agendamento
- **Entao** `SCHEDULING_CONTEXT_ACTIVE` permanece falso
- **E** `get_availability()` nao pode ser chamado.

#### AC-036 — Intencao real de agendar ativa contexto

- **Dado** que o paciente quer marcar consulta ou pergunta por horarios
- **Quando** a mensagem demonstra necessidade real de disponibilidade
- **Entao** o runtime pode ativar `SCHEDULING_CONTEXT_ACTIVE`.

#### AC-037 — Guarda bloqueia disponibilidade fora do contexto

- **Dado** que o LLM ou graph tenta chamar `consultar_agenda`
- **Quando** `SCHEDULING_CONTEXT_ACTIVE` nao esta ativo ou a intencao nao exige disponibilidade
- **Entao** uma guarda deterministica bloqueia `get_availability()`.

#### AC-038 — Disponibilidade vem do CalendarProvider

- **Dado** que o contexto de agendamento esta ativo
- **Quando** o runtime consulta disponibilidade
- **Entao** ele chama `CalendarProvider.get_availability()`
- **E** nunca inventa horarios.

### US-010 — Agenda usa providers desacoplados

Como arquiteto, quero providers para agenda, para trocar Google Calendar, Doctoralia ou outro fornecedor sem alterar o grafo.

#### AC-039 — CalendarProvider define operacoes de agenda

- **Dado** que uma integracao de agenda sera criada
- **Quando** o runtime usa agenda
- **Entao** ele depende de uma interface com `get_availability`, `create_appointment`, `reschedule_appointment` e `cancel_appointment`.

### US-011 — CRM e atualizado progressivamente

Como operador comercial, quero que o agente atualize CRM com informacoes confiaveis, para reduzir retrabalho sem inventar dados.

#### AC-040 — CRMProvider define operacoes progressivas

- **Dado** que uma integracao de CRM sera criada
- **Quando** o runtime usa CRM
- **Entao** ele depende de uma interface com `upsert_contact`, `update_stage`, `update_fields` e `add_note`.

#### AC-041 — CRM nao recebe dados inventados

- **Dado** que uma informacao ainda nao foi fornecida ou derivada por regra autorizada
- **Quando** o runtime monta atualizacao de CRM
- **Entao** campos ausentes nao sao preenchidos artificialmente.

### US-012 — RAG hibrido respeita isolamento e grounding

Como paciente, quero respostas factuais somente com evidencias autorizadas, para evitar alucinacao.

#### AC-042 — Retrieval exige organizationId

- **Dado** que o runtime executa retrieval documental
- **Quando** a busca e solicitada
- **Entao** `organizationId` e obrigatorio
- **E** resultados de outras organizacoes sao rejeitados.

#### AC-043 — Retrieval hibrido combina lexical e vetorial

- **Dado** que uma pergunta factual precisa de evidencias
- **Quando** o runtime busca documentos
- **Entao** ele executa busca lexical e vetorial por provider
- **E** combina resultados sem tratar score como autorizacao final.

#### AC-044 — Score alto nao aprova resposta sem grounding

- **Dado** que retrieval retornou resultado com score alto
- **Quando** a resposta factual seria enviada
- **Entao** grounding precisa retornar `PASS`
- **E** falha de grounding resulta em `HUMAN_HANDOFF_REQUIRED`.

### US-013 — Observabilidade nao substitui auditoria de negocio

Como auditor, quero eventos criticos persistidos no dominio proprio, para nao depender apenas do LangSmith.

#### AC-045 — Runtime registra evento de auditoria operacional

- **Dado** que o graph toma uma decisao relevante
- **Quando** ha tool call, grounding, erro ou handoff
- **Entao** o runtime registra evento com conversa, organizacao, intencao, decisao, tool, grounding, handoff e timestamp.

#### AC-046 — LangSmith e opcional para observabilidade

- **Dado** que LangSmith esta indisponivel ou sem credenciais
- **Quando** o runtime executa
- **Entao** a auditoria de negocio continua funcionando no dominio proprio.

### US-014 — Runtime usa LangGraph como orquestrador

Como arquiteto, quero um grafo de execucao em vez de um prompt gigante, para controlar nodes e transicoes testaveis.

#### AC-047 — Grafo possui nodes conceituais separados

- **Dado** que o runtime e construido
- **Quando** sua topologia e inspecionada
- **Entao** existem nodes separados para interpretar mensagem, decidir rota, executar tool, fazer grounding e handoff.

#### AC-048 — Canal WhatsApp fica fora do runtime inicial

- **Dado** que a feature atual implementa o runtime isolado
- **Quando** o codigo e inspecionado
- **Entao** nao existe dependencia obrigatoria de WhatsApp para testar o agente.

## Suposicoes

| ID | Suposicao | Status |
|---|---|---|
| ASM-007 | O runtime pode ser implementado inicialmente com providers em memoria/fakes para testes, mantendo interfaces para provedores reais futuros. | confirmada |
| ASM-008 | O comando de teste ONP pode continuar usando `node --test`, com testes Node executando codigo Python por subprocesso ate existir runner Python TAP dedicado. | confirmada |

## Perguntas em aberto

Nenhuma pergunta bloqueante para a fundacao isolada desta feature.

Decisoes futuras fora do escopo atual:

- fornecedor real de agenda;
- CRM real e schema definitivo;
- credenciais de Supabase, LangSmith, LLM e providers externos;
- contrato exato do canal WhatsApp.
