# Product Rules — ai-customer-service

## Regra 1 — Atendimento orientado por fonte autorizada

Respostas factuais sobre clinica, profissionais, procedimentos, condicoes comerciais, orientacoes clinicas, agenda, politicas ou atendimento devem ser suportadas por uma fonte autorizada.

O atendimento final ao paciente nao pode expor detalhes internos do sistema, incluindo:

- base de conhecimento;
- documentos internos;
- RAG;
- retrieval;
- ausencia de evidencia;
- score de busca;
- falha de busca;
- informacao nao encontrada.

## Regra 2 — Linguagem final sem diagnostico tecnico

Quando o sistema nao tiver suporte suficiente para responder uma pergunta factual relevante, a mensagem ao paciente nao deve dizer que a IA nao sabe, nao encontrou a informacao, nao possui a informacao ou que a informacao nao esta na base.

Mensagens como "Nao encontrei essa informacao na base disponivel" sao proibidas no atendimento final.

## Regra 3 — Perguntas sem suporte suficiente exigem handoff

Quando o paciente fizer uma pergunta factual relevante sobre a clinica, profissional, procedimento, condicao comercial ou atendimento e a resposta nao estiver suficientemente suportada por uma fonte autorizada, o sistema deve classificar internamente a situacao como:

```text
HUMAN_HANDOFF_REQUIRED
```

Nesse caso, a IA nao deve tentar responder por inferencia. Ela pode enviar apenas uma mensagem natural de transicao previamente autorizada pela clinica, sem mencionar limitacoes tecnicas.

Exemplo conceitual de transicao:

```text
Vou encaminhar essa duvida para nossa equipe para te orientar certinho.
```

A mensagem definitiva deve ser configuravel por clinica.

## Regra 4 — Excecao deterministica para existencia de procedimento

Perguntas diretas sobre se a clinica realiza determinado procedimento devem consultar o catalogo autorizado, ativo e aprovado da clinica.

O catalogo de procedimentos e tratado como lista positiva, completa e fechada apenas para a existencia do procedimento:

```text
PROCEDURE_CATALOG
```

Se o procedimento perguntado nao estiver presente nesse catalogo fechado, o sistema pode responder que a clinica atualmente nao realiza o procedimento.

Essa resposta negativa deve ser resultado deterministico da regra de dominio, nao uma conclusao livre do LLM.

## Regra 5 — Nao generalizar ausencia como negativa

A regra "nao esta cadastrado = nao existe" vale somente para entidades explicitamente marcadas como catalogo fechado.

Inicialmente, a unica entidade com essa regra e:

```text
PROCEDURE_CATALOG
```

Nao aplicar essa inferencia a:

- precos;
- formas de pagamento;
- horarios;
- contraindicações;
- preparacao;
- duracao;
- recuperacao;
- profissionais;
- cobertura de convenio;
- parcelamento;
- politicas;
- condicoes especiais;
- disponibilidade;
- informacoes clinicas;
- qualquer outro atributo.

## Regra 6 — Distinguir existencia da entidade e atributo da entidade

O sistema deve classificar a pergunta antes de decidir se ausencia pode ser usada como evidencia.

### ENTITY_EXISTENCE

Perguntas sobre existencia de procedimento, como "Voces fazem botox?", devem ser classificadas como:

```text
intent_type = ENTITY_EXISTENCE
entity_type = PROCEDURE
source = PROCEDURE_CATALOG
```

Se o procedimento nao estiver no catalogo fechado autorizado:

```text
answer = NOT_OFFERED
```

### ENTITY_ATTRIBUTE

Perguntas sobre atributos do procedimento, como preco, parcelamento, preparo, recuperacao, duracao, disponibilidade ou contraindicações, devem ser classificadas como:

```text
intent_type = ENTITY_ATTRIBUTE
entity_type = PROCEDURE
attribute = <ATTRIBUTE>
```

Se o procedimento existir, mas o atributo nao estiver disponivel em fonte autorizada:

```text
HUMAN_HANDOFF_REQUIRED
```

O sistema nao pode inferir uma negativa, por exemplo "Nao parcelamos", nem expor ausencia de informacao, por exemplo "Nao encontrei informacao sobre parcelamento".

## Fluxo conceitual

```text
Mensagem do paciente
        ↓
Identificar intencao
        ↓
E pergunta sobre existencia de procedimento?
        │
        ├── SIM
        │     ↓
        │ consultar catalogo fechado
        │     ↓
        │ procedimento existe?
        │     ├── SIM → continuar atendimento
        │     └── NAO → responder que nao realiza
        │
        └── NAO
              ↓
        determinar fonte necessaria
              ↓
        recuperar evidencias / tools
              ↓
        informacao suficiente?
              ├── SIM → gerar + validar resposta
              └── NAO → HUMAN_HANDOFF_REQUIRED
```
