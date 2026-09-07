# Spec: AI Commercial Agent Playbook

> feature: ai-commercial-agent-playbook
> status: em-implementacao

## Contexto

Criar uma camada central e reutilizavel de comportamento comercial para agentes de atendimento da Fluxity.

Esta feature separa:

- camada global: como vender, conduzir descoberta, qualificar, tratar objecoes, reduzir fadiga e propor proximo passo;
- camada da organizacao: o que pode afirmar sobre clinica, medico, procedimento, preco, agenda, politicas e integracoes.

O playbook comercial nao e fonte factual autorizada. Ele orienta conduta, ritmo e proxima acao. Fatos continuam vindo de RAG, catalogo de procedimentos, configuracao autorizada ou tools/APIs da organizacao.

## Arquitetura

```text
Agent Runtime
├── Commercial Playbook Global
│   ├── abertura
│   ├── descoberta
│   ├── qualificacao
│   ├── progressao comercial
│   ├── geracao de valor
│   ├── objecoes
│   ├── CTA
│   ├── agendamento
│   ├── fadiga conversacional
│   └── handoff
│
└── Organization Configuration
    ├── assistant_name
    ├── clinic_name
    ├── doctor_name
    ├── locations
    ├── business_hours
    ├── assistant_role
    ├── tone
    ├── sales_goal
    ├── primary_conversion_action
    ├── max_discovery_depth
    ├── cta_style
    ├── appointment_flow
    ├── procedure catalog
    ├── knowledge/RAG
    └── tools/APIs
```

O modulo central esperado fica em `ai_agent_runtime.commercial` e e consumido pelo runtime. Providers WhatsApp, incluindo Z-API, Meta e Evolution, nao devem conter logica comercial especifica.

## Historias

### US-074 — Playbook comercial global reutilizavel

Como arquiteto da plataforma, quero uma camada comercial central, para que qualquer agente ou canal herde o mesmo metodo de venda sem acoplar regras a uma clinica ou provider.

#### AC-254 — Playbook mora fora de Z-API e providers

- **Dado** o runtime e os providers WhatsApp existentes
- **Quando** a camada comercial e inspecionada
- **Entao** a politica comercial fica em modulo central reutilizavel e `zapi_server.py` apenas consome esse modulo, sem hardcodear metodo comercial especifico da Z-API ou de uma clinica.

#### AC-255 — Playbook nao autoriza fatos da organizacao

- **Dado** uma resposta comercial sem evidencia factual autorizada
- **Quando** o playbook decide proxima acao
- **Entao** ele pode orientar perguntas, CTA e tratamento de objecao, mas nao autoriza afirmar preco, tecnica, resultado, procedimento, medico, politica ou agenda.

### US-075 — Estado comercial estruturado

Como agente comercial, quero estado comercial explicito, para decidir se devo perguntar, gerar valor, propor proximo passo, agendar ou pedir humano.

#### AC-256 — Estado comercial contem campos de decisao

- **Dado** uma conversa processada pelo runtime
- **Quando** o playbook comercial avalia o turno
- **Entao** o estado contem `sales_stage`, `discovery_question_count`, `discovery_depth`, `minimum_discovery_complete`, `patient_need_summary`, `patient_engagement`, `conversation_fatigue`, `objection_state`, `appointment_readiness` e `next_best_action`.

#### AC-257 — Next best action e estruturado

- **Dado** o estado comercial calculado
- **Quando** o runtime registra o turno
- **Entao** `next_best_action` usa valor estruturado como `ASK_DISCOVERY`, `BUILD_VALUE`, `PROPOSE_NEXT_STEP`, `ANSWER_FACTUAL`, `HANDLE_OBJECTION`, `SCHEDULE` ou `HUMAN_HANDOFF`.

### US-076 — Descoberta comercial eficiente

Como paciente, quero que a conversa avance quando minha necessidade ja estiver clara, para nao passar por interrogatorio.

#### AC-258 — Minimum discovery complete detecta suficiência

- **Dado** o paciente informou interesse/procedimento, principal incomodo e contexto ou motivacao relevante
- **Quando** o playbook avalia a conversa
- **Entao** `minimum_discovery_complete=true` e a proxima acao deixa de ser apenas `ASK_DISCOVERY`.

#### AC-259 — Descoberta nao vira checklist rigido

- **Dado** que algumas informacoes como idade, urgencia, tentativa anterior ou expectativa ainda estao ausentes
- **Quando** a necessidade comercial ja esta suficiente
- **Entao** o playbook nao exige todos os campos opcionais antes de avancar.

#### AC-260 — Limite de perguntas evita interrogatorio

- **Dado** duas ou tres perguntas de descoberta consecutivas
- **Quando** a necessidade ja esta suficientemente compreendida ou a fadiga aumentou
- **Entao** a proxima acao prioriza `BUILD_VALUE` ou `PROPOSE_NEXT_STEP` em vez de continuar perguntando por curiosidade.

### US-077 — Abertura parametrizada por organizacao

Como organizacao atendida, quero configurar nome, papel, clinica, profissional, unidades e horarios, para que o primeiro contato seja natural sem inventar identidade ou fatos operacionais.

#### AC-261 — Primeiro contato apresenta assistente quando configurado

- **Dado** `assistant_name`, `assistant_role`, `clinic_name`, `doctor_name`, `locations` e `business_hours` configurados
- **Quando** o primeiro contato real da conversa e processado
- **Entao** o prompt orienta apresentacao natural e contexto organizacional usando esses dados autorizados.

#### AC-262 — Apresentacao nao repete em turnos seguintes

- **Dado** uma conversa com historico persistido
- **Quando** novo turno chega
- **Entao** o prompt nao orienta repetir a apresentacao inicial.

#### AC-263 — Dados ausentes nao sao inventados

- **Dado** configuracao de organizacao incompleta
- **Quando** o primeiro contato e processado
- **Entao** o playbook usa abertura segura sem inventar nome de assistente, papel, clinica, profissional, unidade ou horario.

### US-078 — Fadiga e repeticao sao controladas

Como paciente, quero respostas que reconhecam meu contexto sem repetir tudo, para sentir progresso na conversa.

#### AC-264 — Repeticao excessiva e desencorajada

- **Dado** uma conversa multiturno com dados ja coletados
- **Quando** o prompt comercial e composto
- **Entao** ele instrui reconhecimento breve e evita recapitular todo o historico a cada turno.

#### AC-265 — Fadiga conversacional aumenta com respostas curtas repetidas

- **Dado** tres respostas curtas consecutivas ou muitos turnos em descoberta
- **Quando** o playbook avalia a conversa
- **Entao** `conversation_fatigue` aumenta para `MEDIUM` ou `HIGH`.

#### AC-266 — Fadiga alta reduz perguntas

- **Dado** `conversation_fatigue=HIGH`
- **Quando** o playbook escolhe `next_best_action`
- **Entao** ele para descoberta por curiosidade e prioriza avancar com resumo breve, valor ou proximo passo.

### US-079 — Objeções sao tratadas comercialmente

Como paciente, quero que preocupacoes comerciais sejam tratadas sem handoff desnecessario, para continuar a decisao com seguranca.

#### AC-267 — Objeção nao factual nao vira handoff

- **Dado** mensagem como `esta caro` ou `tenho medo de ficar artificial`
- **Quando** nao ha pedido factual especifico sem evidencia
- **Entao** o playbook classifica objecao/concern e escolhe `HANDLE_OBJECTION`, sem `HUMAN_HANDOFF_REQUIRED` automatico.

#### AC-268 — Pergunta factual continua distinta de objeção

- **Dado** mensagem como `quanto custa?` ou `qual marca voces usam?`
- **Quando** ela exige atributo factual da organizacao
- **Entao** a regra factual existente continua exigindo evidencia/RAG/tool ou handoff silencioso.

### US-080 — CTA e agendamento avancam no momento certo

Como operador comercial, quero que a IA proponha o proximo passo quando ja ha necessidade entendida, para nao esperar reclamacao do paciente.

#### AC-269 — Necessidade suficiente permite ponte de valor

- **Dado** necessidade compreendida e interesse ativo
- **Quando** o playbook calcula o estado
- **Entao** o estagio muda para `NEED_CONFIRMED` ou `VALUE_BRIDGE` e a proxima acao pode ser `BUILD_VALUE`.

#### AC-270 — Proximo passo e proposto sem consulta indevida de agenda

- **Dado** necessidade compreendida, mas sem `SCHEDULING_CONTEXT_ACTIVE`
- **Quando** o playbook escolhe `PROPOSE_NEXT_STEP`
- **Entao** ele pode orientar CTA de avaliacao/consulta, mas nao autoriza inventar disponibilidade nem chamar Calendar fora do contexto aprovado.

### US-081 — Prompt comercial composto com fontes separadas

Como mantenedor, quero uma composicao clara de prompt, para evitar prompt monolitico especifico de uma clinica.

#### AC-271 — Prompt separa safety, playbook, organizacao, evidencia e estado

- **Dado** um turno que sera enviado ao modelo
- **Quando** o prompt e montado
- **Entao** ele contem secoes equivalentes a base safety, commercial playbook, organization configuration, authorized evidence e conversation state.

#### AC-272 — Z-API live usa o mesmo playbook central

- **Dado** uma mensagem processada pelo servidor live Z-API
- **Quando** o prompt e montado
- **Entao** ele usa o estado e as instrucoes do modulo comercial central, nao um prompt comercial paralelo.

### US-089 — Conduta comercial natural e memoria operacional

Como paciente em uma conversa de WhatsApp, quero que a assistente use meu contexto de forma natural e segura, para avancar sem expor limitacoes internas, inventar fatos ou repetir perguntas.

#### AC-318 — Lacunas internas nunca sao verbalizadas ao paciente

- **Dado** uma lacuna factual ou atributo ausente
- **Quando** a assistente puder avancar comercialmente sem inventar o fato
- **Entao** o prompt proibe dizer que nao conseguiu confirmar, nao encontrou na base, nao tem acesso, nao tem informacao, usa RAG/retrieval/documento/evidencia ou que a equipe pode verificar.

#### AC-319 — Atributo tecnico ausente nao autoriza explicacao clinica

- **Dado** pergunta sobre diferenca, subtipo, tecnica ou material sem evidencia autorizada especifica
- **Quando** existir ponte comercial autorizada para avaliacao/planejamento
- **Entao** o playbook orienta conduzir para avaliacao sem afirmar a tecnica ausente nem usar conhecimento clinico geral.

#### AC-320 — Linguagem de WhatsApp evita estilo artificial

- **Dado** o prompt comercial composto
- **Quando** ele orienta a geracao
- **Entao** ele favorece texto simples de WhatsApp e desencoraja travessao, Markdown artificial, negrito com asteriscos, linguagem de SAC e cara de LLM.

#### AC-321 — Agradecimentos e nomes nao viram prefixo automatico

- **Dado** conversas multiturno
- **Quando** o prompt orienta reconhecimento
- **Entao** ele reduz bordoes repetidos como Perfeito, Entendi, Certo, Otimo, Combinado, Voce tem razao e uso recorrente do nome do paciente.

#### AC-322 — Memoria operacional registra dados ja informados

- **Dado** mensagens com unidade, dia, horario ou outros dados operacionais
- **Quando** o playbook avalia o turno
- **Entao** `operational_memory` registra campos conhecidos como `preferred_location`, `preferred_date`, `preferred_time`, `procedure_interest` e `appointment_intent` quando extraiveis.

#### AC-323 — Informacao conhecida nao deve ser perguntada novamente

- **Dado** um dado operacional ja presente em `operational_memory`
- **Quando** a assistente for perguntar o proximo dado
- **Entao** o prompt instrui nao pedir novamente o que ja e conhecido, salvo contradicao, ambiguidade ou confirmacao final.

#### AC-324 — Telefone do WhatsApp entra como dado conhecido

- **Dado** um canal WhatsApp com `contactExternalId` telefonico utilizavel
- **Quando** o playbook avalia o turno
- **Entao** `patient_phone` e preenchido a partir do canal e o prompt proibe perguntar qual e o WhatsApp do paciente.

#### AC-325 — Coleta cadastral agrupa campos faltantes

- **Dado** etapa cadastral com varios campos obrigatorios ainda ausentes
- **Quando** o playbook compoe a politica de coleta
- **Entao** ele orienta pedir os campos faltantes em uma mensagem ou bloco logico, sem dividir em seis turnos independentes.

#### AC-326 — Campos cadastrais conhecidos nao sao repetidos

- **Dado** campos como nome, email, CPF, RG, CEP ou endereco ja extraidos
- **Quando** a politica de coleta e calculada
- **Entao** ela pede somente campos faltantes.

#### AC-327 — Escolha tecnica prematura nao e pre-requisito

- **Dado** interesse geral suficiente em lentes, implante, protese, harmonizacao ou procedimento semelhante
- **Quando** o paciente quer avancar para avaliacao
- **Entao** o playbook nao obriga escolher subtipo tecnico antes da consulta, salvo necessidade real de roteamento ou regra da organizacao.

#### AC-328 — Estado de agendamento separa intencao de booking confirmado

- **Dado** intencao, unidade, data e horario informados
- **Quando** ainda nao ha retorno de ferramenta confirmando o agendamento
- **Entao** `scheduling_state` nao e `BOOKED` e o prompt proibe linguagem definitiva como agendado, marcado ou registrado.

#### AC-329 — Correcoes de tratamento ocorrem uma vez

- **Dado** correcao explicita de nome, genero linguistico, pronome ou preferencia de tratamento
- **Quando** a correcao aparece no turno atual
- **Entao** `correction_state.acknowledge_once=true`; em turnos seguintes a preferencia permanece, mas a correcao nao e verbalizada de novo.

## Fora de escopo

- Criar respostas fixas por procedimento ou por clinica especifica.
- Enfraquecer grounding, RAG, handoff, politica medica, Calendar ou isolamento cross-org.
- Implementar CRM ou Central de Atendimento.
- Alterar infraestrutura Z-API, Meta ou Evolution.
- Criar LLM judge obrigatorio para avaliacao.
- Definir configuracao final de todas as organizacoes reais.

## Suposicoes

| ID | Suposicao | Status | Resolucao |
|---|---|---|---|
| ASM-036 | A camada comercial global deve viver no runtime/core, nao no canal WhatsApp nem em provider especifico. | confirmada | Derivado das specs existentes: WhatsApp e canal, Z-API e provider, runtime e o cerebro do agente. |
| ASM-037 | Configuracao de organizacao pode comecar como dataclass/env/contexto injetado, antes de existir painel administrativo. | confirmada | Permite personalizacao sem iniciar CRM ou UI. |
| ASM-038 | A avaliacao comercial pode usar assercoes deterministicas para estado, contagem de perguntas, fadiga e proximas acoes. | confirmada | O prompt pede evitar dependencia exclusiva de LLM judge quando possivel. |

## Perguntas em aberto

Nenhuma pergunta bloqueante para esta implementacao central.

Decisoes futuras fora deste escopo:

- nomes reais de assistentes por organizacao;
- copy final aprovada por marca;
- limites comerciais por especialidade;
- politica final de transferencia entre IA e humano na Central de Atendimento.
