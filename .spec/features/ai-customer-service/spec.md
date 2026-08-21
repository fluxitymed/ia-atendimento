# AI Customer Service

> feature: ai-customer-service
> status: rascunho

## Objetivo

Construir uma IA de atendimento comercial para clinicas, inicialmente via WhatsApp, com respostas factuais estritamente fundamentadas em fontes autorizadas.

O conhecimento pre-treinado do LLM nao e uma fonte autorizada de fatos sobre a clinica.

Esta especificacao funciona como documento principal da feature. Os detalhes permanecem nos documentos especializados:

- `overview.md`: visao geral da feature.
- `product-rules.md`: regras de produto e limites de linguagem no atendimento.
- `rag-contract.md`: contrato de fontes, retrieval, mundo fechado e grounding.
- `ingestion-contract.md`: contrato de ingestao, aprovacao, publicacao, versionamento e proveniencia documental.
- `data-model.md`: modelo conceitual de documentos, versoes, chunks, indexacao, evidencias e claims.
- `chunking-contract.md`: estrategia de chunking semantico, preservacao de contexto e qualidade dos chunks.
- `acceptance-criteria.md`: criterios de aceite detalhados ja aprovados.
- `tasks.md`: tarefas futuras de implementacao.

## Arquitetura conceitual

```text
Mensagem
↓
Estado da conversa
↓
Classificacao/intencao
↓
Decisao da fonte
├── conhecimento estatico → RAG
├── dado dinamico/acao → Tool/API
└── informacao sem suporte → Handoff humano
↓
Grounding
↓
Resposta
```

## Escopo atual

Esta feature esta em fase de especificacao.

Ainda nao existem:

- agente implementado;
- LangGraph;
- vector database;
- embeddings;
- ingestion pipeline;
- retrieval;
- grounding validator;
- WhatsApp;
- handoff implementado;
- tools;
- integracao com CRM.
- schema SQL, migrations ou banco documental.
- chunker, tokenizer, embeddings ou estrategia final de overlap.

## Regras criticas

As regras completas ficam em `product-rules.md`.

Resumo normativo:

- ausencia de informacao factual relevante deve gerar `HUMAN_HANDOFF_REQUIRED`;
- a resposta final ao paciente nunca deve expor termos internos como RAG, retrieval, base, documentos, score, falha de busca ou falta de evidencia;
- `PROCEDURE_CATALOG` e inicialmente uma fonte `CLOSED_WORLD`;
- ausencia de procedimento em catalogo fechado pode significar "nao oferecido";
- ausencia de atributo de entidade nao pode ser interpretada negativamente;
- o sistema deve distinguir `ENTITY_EXISTENCE` de `ENTITY_ATTRIBUTE`;
- informacao dinamica deve vir de tools/APIs autorizadas;
- cross-organization retrieval e proibido.

## RAG e grounding

O contrato completo fica em `rag-contract.md`.

O RAG pode recuperar conhecimento estatico autorizado, mas retrieval nao e autorizacao final de resposta.

```text
retrieval score alto != resposta autorizada
```

A resposta devera passar futuramente por validacao de grounding antes de ser enviada ao paciente.

Ausencia de chunks, score baixo ou falha de retrieval nao autorizam afirmacao negativa. A excecao so existe para fonte estruturada explicitamente marcada como `CLOSED_WORLD` no escopo definido pelo dominio.

## Ingestao documental

O contrato completo fica em `ingestion-contract.md`.

A IA jamais pode responder utilizando simplesmente qualquer arquivo enviado para o sistema.

```text
uploaded != approved
processed != authorized
```

Somente conteudo publicado, vigente, aprovado e pertencente a organizacao correta pode participar do retrieval de producao.

Lifecycle documental:

```text
DRAFT
↓
PROCESSING
↓
PROCESSING_FAILED
↓
REVIEW_REQUIRED
↓
APPROVED
↓
PUBLISHED
↓
SUPERSEDED / INACTIVE
```

`PUBLISHED` e o unico estado que pode fundamentar respostas em producao. Publicacao exige acao explicita de pessoa autorizada, deve preservar `approvedBy`, `approvedAt`, `publishedBy` e `publishedAt`, e deve manter isolamento por `organizationId` desde a origem.

## Modelo de dados documental

O modelo completo fica em `data-model.md`.

O conhecimento documental deve separar:

```text
DOCUMENT
↓
DOCUMENT_VERSION
↓
NORMALIZED_CONTENT
↓
CHUNK
↓
RETRIEVAL_INDEX_ENTRY
↓
RETRIEVAL_EVIDENCE
↓
AI_RESPONSE / CLAIM
```

`DOCUMENT` representa a identidade logica duradoura. `DOCUMENT_VERSION` representa uma edicao especifica. `CHUNK` nao possui autoridade propria e herda elegibilidade da versao documental.

O modelo conceitual tambem define que `knowledge base != patient memory`: a base documental armazena conhecimento autorizado da clinica, nao memoria individual de pacientes.

## Chunking semantico

O contrato completo fica em `chunking-contract.md`.

O chunking deve preservar integridade semantica:

```text
semantic integrity > fixed size
```

Tamanho, tokens e overlap sao restricoes tecnicas futuras, nao a regra principal de fronteira. Chunks devem preservar entidade, atributo, condicao, excecao, escopo, vigencia, profissional, procedimento, unidade, preco e relacoes entre afirmacoes.

O contrato define `SEMANTIC_ATOMIC_UNIT`, chunks `SELF_CONTAINED`, heranca de contexto, `sectionPath`, `parentChunkId`, `semanticType`, `chunkingStrategy` e `chunkingVersion`.

Para `PROCEDURE_CATALOG`:

```text
absence detection != vector retrieval
```

Ausencia de procedimento deve continuar vindo de consulta deterministica ao catalogo fechado vigente e completo, nao de ausencia de chunk.

## Handoff humano

Quando a evidencia necessaria nao estiver disponivel em fonte autorizada, o sistema deve classificar internamente:

```text
HUMAN_HANDOFF_REQUIRED
```

O atendimento devera ser assumido por humano com preservacao do contexto da conversa, para evitar que o paciente precise repetir informacoes ja fornecidas.

### US-001 — Paciente recebe resposta factual fundamentada

Como paciente em atendimento comercial, quero receber respostas factuais sobre a clinica somente quando houver fonte autorizada suficiente, para evitar orientacoes inventadas ou inseguras.

#### AC-001 — Informacao desconhecida exige handoff

- **Dado** que o paciente fez uma pergunta factual relevante sobre clinica, profissional, procedimento, condicao comercial ou atendimento
- **Quando** a informacao necessaria nao estiver disponivel em fonte autorizada
- **Entao** o sistema classifica internamente a situacao como `HUMAN_HANDOFF_REQUIRED`
- **E** a resposta final nao expoe ausencia de informacao, ausencia de evidencia ou detalhes tecnicos de busca.

#### AC-005 — Atendimento final sem linguagem tecnica interna

- **Dado** que uma resposta sera enviada ao paciente
- **Quando** a resposta for gerada para o atendimento final
- **Entao** ela nao menciona RAG, base, documentos, retrieval, evidencia insuficiente, informacao nao encontrada, score de busca ou falha de busca.

### US-002 — Paciente pergunta se a clinica realiza um procedimento

Como paciente, quero saber se a clinica realiza determinado procedimento, para decidir se devo continuar o atendimento.

#### AC-002 — Procedimento ausente em catalogo fechado pode ser informado como nao oferecido

- **Dado** que o paciente perguntou diretamente se a clinica realiza um procedimento
- **E** existe um catalogo de procedimentos completo, ativo, aprovado e marcado como `CLOSED_WORLD`
- **Quando** o procedimento nao estiver cadastrado nesse catalogo
- **Entao** a IA pode informar que a clinica atualmente nao realiza o procedimento.

#### AC-003 — Apenas catalogo fechado usa ausencia como evidencia negativa

- **Dado** que uma resposta negativa depende da ausencia de uma entidade
- **Quando** a fonte consultada nao estiver explicitamente marcada como `CLOSED_WORLD` para aquele escopo
- **Entao** o sistema nao usa a ausencia como evidencia negativa
- **E** segue o fluxo de informacao insuficiente.

### US-003 — Paciente pergunta atributos de procedimento

Como paciente, quero receber informacoes sobre atributos de um procedimento somente quando elas estiverem autorizadas, para nao tomar decisoes com base em inferencias.

#### AC-004 — Atributos ausentes exigem handoff

- **Dado** que um procedimento existe no catalogo autorizado
- **Quando** o paciente pergunta sobre um atributo do procedimento, como preco, parcelamento, preparo, recuperacao, duracao, disponibilidade ou contraindicações
- **E** esse atributo nao esta disponivel em fonte autorizada
- **Entao** o sistema classifica a situacao como `HUMAN_HANDOFF_REQUIRED`
- **E** nao responde com uma negativa inferida.

### US-004 — Humano assume conversa com contexto

Como atendente humano, quero receber o contexto da conversa ao assumir um handoff, para continuar o atendimento sem pedir novamente dados ja informados pelo paciente.

#### AC-006 — Handoff preserva contexto

- **Dado** que o sistema classificou a situacao como `HUMAN_HANDOFF_REQUIRED`
- **Quando** o atendimento for transferido para uma pessoa
- **Entao** o contexto da conversa e preservado para que o humano consiga assumir sem solicitar novamente informacoes ja fornecidas pelo paciente.

#### AC-007 — Mensagem de transicao configuravel

- **Dado** que o sistema classificou a situacao como `HUMAN_HANDOFF_REQUIRED`
- **Quando** uma mensagem de transicao for enviada ao paciente
- **Entao** a mensagem usa texto autorizado e configuravel pela clinica
- **E** nao menciona limitacoes tecnicas ou ausencia de informacao.

### US-005 — Administrador publica conhecimento autorizado

Como administrador autorizado da clinica, quero que documentos passem por ingestao, validacao, aprovacao e publicacao antes de alimentar a IA, para impedir que conteudo nao autorizado fundamente respostas a pacientes.

#### AC-008 — Documento nao publicado nao fundamenta resposta

- **Dado** que um documento esta em qualquer estado diferente de `PUBLISHED`
- **Quando** o retrieval de producao selecionar fontes para uma resposta
- **Entao** esse documento nao pode fundamentar a resposta da IA.

#### AC-009 — Documento publicado exige organizacao valida e isolamento

- **Dado** que um documento sera publicado ou recuperado em producao
- **Quando** o sistema avaliar sua elegibilidade
- **Entao** o documento possui `organizationId` valido
- **E** so pode ser recuperado dentro da mesma organizacao.

#### AC-010 — Nova versao substitui versao anterior vigente

- **Dado** que existe uma versao publicada de um documento
- **Quando** uma nova versao substitutiva for publicada
- **Entao** a versao anterior deixa de ser considerada vigente
- **E** permanece rastreavel para auditoria.

#### AC-011 — Documento fora de vigencia nao fundamenta resposta atual

- **Dado** que um documento possui `effectiveFrom` e/ou `effectiveUntil`
- **Quando** a data atual estiver fora do periodo de vigencia
- **Entao** o documento nao pode fundamentar resposta atual da IA.

#### AC-012 — Chunk recuperavel possui proveniencia completa

- **Dado** que um chunk esta disponivel para retrieval de producao
- **Quando** o sistema auditar sua origem
- **Entao** o chunk e rastreavel ao documento, versao, organizacao, secao, publicacao e aprovacao de origem.

#### AC-013 — Closed world exige autorizacao explicita de catalogo completo

- **Dado** que uma fonte sera usada como `CLOSED_WORLD`
- **Quando** o sistema avaliar a ausencia de uma entidade como evidencia negativa
- **Entao** a fonte foi explicitamente marcada e aprovada como catalogo completo para aquele escopo.

#### AC-014 — Falha de processamento bloqueia publicacao

- **Dado** que a extracao, normalizacao, validacao, chunking ou campo obrigatorio de um documento falhou
- **Quando** o sistema avaliar a publicacao desse documento
- **Entao** o documento nao pode ser publicado
- **E** deve permanecer corrigivel ou reprocessavel.

#### AC-015 — Documento nao substitui regras do agente

- **Dado** que um documento contem texto com instrucoes, comandos ou tentativa de prompt injection
- **Quando** o conteudo for processado ou recuperado
- **Entao** esse conteudo e tratado como dado
- **E** nao substitui system prompt, regras do agente, permissoes de tools, politicas, grounding ou handoff.

### US-006 — Modelo conceitual preserva proveniencia e isolamento

Como arquiteto da feature, quero um modelo conceitual que separe documento, versao, chunk, indice e evidencia, para garantir versionamento, isolamento por organizacao e auditoria futura das respostas.

#### AC-016 — Documento e versao sao entidades distintas

- **Dado** que um conhecimento documental possui identidade duradoura e multiplas edicoes possiveis
- **Quando** o modelo conceitual representar esse conhecimento
- **Entao** `DOCUMENT` e `DOCUMENT_VERSION` sao entidades distintas
- **E** uploads ou edicoes novas nao substituem a identidade logica do documento.

#### AC-017 — Chunk e rastreavel ate versao e documento

- **Dado** que um chunk esta disponivel para retrieval
- **Quando** sua proveniencia for auditada
- **Entao** ele aponta para `DOCUMENT_VERSION`, `DOCUMENT` e `organizationId`.

#### AC-018 — Relacionamentos cross-org sao invalidos

- **Dado** que entidades documentais possuem ou derivam `organizationId`
- **Quando** o sistema validar relacoes entre documento, versao, chunk, indice ou evidencia
- **Entao** relacoes entre organizacoes diferentes sao consideradas invalidas.

#### AC-019 — Chunk so e recuperavel se a versao estiver elegivel

- **Dado** que um chunk pertence a uma versao documental
- **Quando** o retrieval de producao avaliar esse chunk
- **Entao** ele so participa se a versao estiver publicada, vigente, processada validamente e isolada na organizacao ativa.

#### AC-020 — Reindexacao tecnica nao cria nova versao documental

- **Dado** que o conteudo autorizado de uma versao documental nao mudou
- **Quando** o sistema executar `reembed` ou `reindex`
- **Entao** a mudanca de indexacao nao cria automaticamente nova `DOCUMENT_VERSION`.

#### AC-021 — Closed world e autorizado por versao

- **Dado** que uma fonte sera usada como `CLOSED_WORLD`
- **Quando** o modelo conceitual registrar essa autorizacao
- **Entao** o modo efetivo e a aprovacao de completude pertencem a `DOCUMENT_VERSION`.

#### AC-022 — Versao substitutiva nao concorre como verdade atual

- **Dado** que duas versoes pertencem ao mesmo documento logico e uma substitui a outra
- **Quando** a nova versao se tornar vigente
- **Entao** a versao substituida nao pode concorrer como fonte atual equivalente.

#### AC-023 — Base documental nao armazena memoria individual de pacientes

- **Dado** que a IA atendera pacientes
- **Quando** o modelo documental armazenar conhecimento para retrieval
- **Entao** ele armazena conhecimento autorizado da clinica
- **E** nao historico individual ou memoria de pacientes.

### US-007 — Chunking preserva significado e contexto

Como arquiteto da feature, quero uma estrategia de chunking semantico, para que retrieval e grounding recebam unidades recuperaveis que preservem entidade, atributo, condicao, excecao e proveniencia.

#### AC-024 — Chunk preserva integridade semantica

- **Dado** que um documento autorizado contem uma entidade e seus atributos relacionados
- **Quando** o conteudo for transformado em chunks
- **Entao** o chunk nao separa entidade de atributo de forma que altere ou torne ambiguo o significado.

#### AC-025 — Regra e excecao permanecem contextualizadas

- **Dado** que uma excecao modifica diretamente uma regra
- **Quando** o chunking produzir unidades recuperaveis
- **Entao** a excecao permanece recuperavel junto do contexto da regra.

#### AC-026 — FAQ preserva pergunta e resposta

- **Dado** que uma FAQ contem pergunta e resposta relacionadas
- **Quando** o chunking processar essa FAQ
- **Entao** pergunta e resposta nao sao separadas de forma ambigua.

#### AC-027 — Tabelas herdam cabecalhos necessarios

- **Dado** que uma informacao vem de linha ou celula de tabela
- **Quando** ela for normalizada em chunk
- **Entao** o chunk herda os cabecalhos necessarios para interpretar o valor.

#### AC-028 — Negacoes e qualifiers sao preservados

- **Dado** que o texto original contem negacao, condicao ou qualifier como nao, exceto, somente ou contraindicado
- **Quando** o conteudo for normalizado ou chunkado
- **Entao** a negacao, condicao ou qualifier nao e removido nem alterado.

#### AC-029 — Contexto ancestral pode ser herdado sem invencao

- **Dado** que uma informacao depende de heading, tabela, lista ou escopo ancestral
- **Quando** o chunk for enriquecido com contexto
- **Entao** o contexto herdado vem apenas de informacao presente e inequivoca no documento.

#### AC-030 — Catalogo fechado nao depende de ausencia de chunk

- **Dado** que o paciente pergunta se a clinica realiza um procedimento
- **Quando** o sistema avaliar ausencia no `PROCEDURE_CATALOG`
- **Entao** a decisao nao usa ausencia de chunk ou retrieval vetorial como evidencia de `NOT_OFFERED`.

#### AC-031 — Chunk aponta para origem auditavel

- **Dado** que um chunk foi criado a partir de documento autorizado
- **Quando** sua origem for auditada
- **Entao** ele aponta para documento, versao, organizacao, sectionPath e source span quando tecnicamente aplicavel.

#### AC-032 — Mudanca de estrategia de chunking nao cria nova versao documental

- **Dado** que o conteudo autorizado de uma versao documental nao mudou
- **Quando** o sistema aplicar nova `chunkingStrategy` ou `chunkingVersion`
- **Entao** essa mudanca tecnica nao cria automaticamente nova `DOCUMENT_VERSION`.

## Suposições

| id | suposição | status | resolução |
|---|---|---|---|
| ASM-001 | `PROCEDURE_CATALOG` e a primeira e unica fonte `CLOSED_WORLD` definida para a feature neste momento. | confirmada | Confirmado pelas regras de produto e pelo contrato RAG atuais. |
| ASM-002 | A feature deve permanecer em fase de especificacao ate existir decisao explicita para iniciar implementacao funcional. | confirmada | Confirmado pelo pedido desta tarefa. |
| ASM-003 | `overview.md` e uma referencia esperada pela estrutura da feature. | confirmada | O arquivo foi criado nesta consolidacao sem acrescentar regras funcionais novas. |
| ASM-004 | O contrato de ingestao define dominio e rastreabilidade, sem fechar schema de banco ou modelo definitivo de permissoes. | confirmada | Confirmado pelo escopo documental da T-002. |
| ASM-005 | O modelo de dados e conceitual e nao define schema SQL, migrations, banco, ORM, storage ou vector database. | confirmada | Confirmado pelo escopo documental da T-003. |
| ASM-006 | A estrategia de chunking e conceitual e nao define tokenizer, tamanho final, overlap final, parser, embeddings ou vector database. | confirmada | Confirmado pelo escopo documental da T-004. |

## Perguntas em aberto

| id | pergunta | status | resposta |
|---|---|---|---|
| Q-001 | Qual sera a mensagem de transicao configuravel padrao por clinica para `HUMAN_HANDOFF_REQUIRED`? | aberta | |
| Q-002 | Quais tools/APIs serao fontes autorizadas para dados dinamicos como agenda, CRM, condicoes comerciais e disponibilidade? | aberta | |
| Q-003 | Quais papeis de usuario poderao aprovar e publicar documentos em cada organizacao? | aberta | |
| Q-004 | Qual dominio futuro armazenara memoria individual de pacientes e historico conversacional? | aberta | |
| Q-005 | Quais limites tecnicos de tokens/caracteres serao adotados por modelo de embedding e janela de contexto? | aberta | |
