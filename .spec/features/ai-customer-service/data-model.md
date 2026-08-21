# Data Model — ai-customer-service

## Objetivo

Este documento define o modelo conceitual de dados que futuramente suportara:

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

Este contrato nao define schema SQL, banco, migrations, ORM, storage, vector database ou classes de implementacao.

A estrategia de criacao de chunks fica em `chunking-contract.md`.

## Principios

- `knowledge base != patient memory`
- `DOCUMENT` e `DOCUMENT_VERSION` sao entidades distintas.
- `CHUNK` nao possui autoridade propria.
- `PUBLISHED != CURRENTLY_USABLE`.
- Reindexacao tecnica nao cria nova versao documental quando o conteudo autorizado nao mudou.
- Toda entidade relevante deve possuir ou derivar inequivocamente `organizationId`.
- Relacionamentos cross-organization sao invalidos.

## DOCUMENT

`DOCUMENT` representa a identidade logica e duradoura de uma informacao da clinica.

Exemplo:

```text
DOCUMENT: Valores de consulta
  VERSION 1: Consulta R$ 400
  VERSION 2: Consulta R$ 500
```

Campos conceituais:

```text
id
organizationId
canonicalKey
documentType
title
description
category
entityScope
closedWorldMode
createdAt
updatedAt
```

Finalidade dos campos:

- `id`: identificador tecnico do documento logico.
- `organizationId`: organizacao proprietaria do documento.
- `canonicalKey`: chave logica estavel dentro da organizacao para evitar duplicacao acidental.
- `documentType`: tipo de conhecimento, como `PROCEDURE_CATALOG`, `PRICING` ou `CLINIC_INFO`.
- `title`: nome humano do documento logico.
- `description`: descricao opcional do escopo.
- `category`: agrupamento operacional opcional.
- `entityScope`: escopo estruturado do assunto quando o documento se refere a uma entidade especifica.
- `closedWorldMode`: politica padrao pretendida para o documento logico, sem dispensar autorizacao versionada.
- `createdAt` e `updatedAt`: rastreabilidade temporal.

### canonicalKey

`canonicalKey` e uma chave logica estavel por organizacao.

Exemplos:

```text
procedure-catalog
general-pricing
payment-policy
clinic-info
doctor-joao-profile
procedure-botox-guidance
```

Conceitualmente:

```text
organizationId + canonicalKey
```

identifica um documento logico. Este contrato nao define constraint SQL.

## DOCUMENT_VERSION

`DOCUMENT_VERSION` representa uma edicao especifica de um `DOCUMENT`.

Campos conceituais:

```text
id
documentId
organizationId
versionNumber
status
sourceType
sourceName
sourceArtifactReference
rawContentReference
extractedContentReference
normalizedContent
checksum
knowledgeMode
closedWorldCompletenessApproved
effectiveFrom
effectiveUntil
approvedBy
approvedAt
publishedBy
publishedAt
supersedesVersionId
processingValid
createdAt
updatedAt
```

Campos que pertencem ao documento logico:

- identidade estavel (`id`);
- organizacao dona (`organizationId`);
- chave logica (`canonicalKey`);
- tipo e escopo esperados (`documentType`, `entityScope`);
- titulo e descricao duradouros.

Campos que pertencem a versao:

- conteudo especifico;
- status do lifecycle;
- numero de versao;
- origem;
- checksum;
- vigencia;
- aprovacao e publicacao;
- completude `CLOSED_WORLD`;
- substituicao de versao anterior;
- referencias a conteudo bruto, extraido e normalizado.

`organizationId` tambem aparece em `DOCUMENT_VERSION` por seguranca e isolamento. Mesmo sendo derivavel via `documentId`, a duplicacao permite consultas isoladas, validacoes defensivas e deteccao de relacoes cross-organization invalidas.

## Estado documental

Lifecycle aprovado:

```text
DRAFT
PROCESSING
PROCESSING_FAILED
REVIEW_REQUIRED
APPROVED
PUBLISHED
SUPERSEDED
INACTIVE
```

Transicoes validas conceituais:

```text
DRAFT → PROCESSING
PROCESSING → REVIEW_REQUIRED
PROCESSING → PROCESSING_FAILED
PROCESSING_FAILED → PROCESSING
REVIEW_REQUIRED → APPROVED
APPROVED → PUBLISHED
PUBLISHED → SUPERSEDED
PUBLISHED → INACTIVE
APPROVED → INACTIVE
```

Substituicao:

```text
PUBLISHED v1
+
PUBLISHED v2
→ v1 SUPERSEDED
→ v2 PUBLISHED
```

Transicoes invalidas conceituais:

```text
DRAFT → PUBLISHED
PROCESSING_FAILED → PUBLISHED
REVIEW_REQUIRED → PUBLISHED
SUPERSEDED → PUBLISHED
INACTIVE → PUBLISHED
```

Excecoes futuras devem ser aprovadas explicitamente em nova regra de dominio.

## Conteudo bruto, extraido e normalizado

O modelo nao deve misturar:

```text
sourceArtifact
extractedContent
normalizedContent
```

- `sourceArtifactReference`: referencia ao arquivo original ou artefato de origem, possivelmente em storage externo.
- `extractedContentReference`: referencia ao texto ou estrutura extraida.
- `normalizedContent`: representacao normalizada aprovada para processamento e chunking.

O contrato nao define storage.

## CHUNK

`CHUNK` representa uma unidade recuperavel derivada de uma versao documental.

Campos conceituais:

```text
id
organizationId
documentId
documentVersionId
chunkIndex
content
sectionPath
semanticType
metadata
contentHash
tokenCount
characterCount
parentChunkId
chunkingStrategy
chunkingVersion
inheritedContext
sourcePage
sourceSection
sourceStartOffset
sourceEndOffset
sourceTable
sourceRow
createdAt
```

`tokenCount`, `characterCount`, `parentChunkId`, `inheritedContext`, source span e versionamento tecnico de chunking sao opcionais conceituais e dependem da estrategia futura de chunking.

### Autoridade do chunk

```text
CHUNK nao possui autoridade propria.
```

O chunk herda validade da `DOCUMENT_VERSION`.

Se a versao estiver `SUPERSEDED`, `INACTIVE`, fora de vigencia, nao publicada ou com processamento invalido, o chunk nao pode ser usado em retrieval de producao.

Nao se deve depender de apagar fisicamente chunks para tornar uma versao invalida.

## Proveniencia

Todo chunk recuperavel deve permitir reconstruir:

```text
chunk
→ documentVersion
→ document
→ organization
```

Metadados obrigatorios recuperaveis por proveniencia:

```text
documentType
title
versionNumber
status
effectiveFrom
effectiveUntil
approvedBy
publishedBy
sectionPath
```

Chunks sem proveniencia completa nao sao elegiveis para retrieval de producao.

## CLOSED_WORLD versionado

Nao inferir `CLOSED_WORLD` apenas por `documentType`.

Campos conceituais:

```text
DOCUMENT.closedWorldMode
DOCUMENT_VERSION.knowledgeMode
DOCUMENT_VERSION.closedWorldCompletenessApproved
```

Decisao:

- `DOCUMENT.closedWorldMode` registra a intencao ou capacidade padrao do documento logico.
- `DOCUMENT_VERSION.knowledgeMode` registra o modo efetivo daquela versao.
- `DOCUMENT_VERSION.closedWorldCompletenessApproved` registra que aquela versao foi aprovada como completa para seu escopo.

Justificativa: uma nova versao pode alterar completude, escopo ou semantica. Portanto a autorizacao de `CLOSED_WORLD` precisa ser versionada.

`PROCEDURE_CATALOG` pode ser `CLOSED_WORLD` somente quando a versao publicada foi explicitamente aprovada como lista oficial e completa de procedimentos atualmente oferecidos pela clinica.

## Escopo de entidades

Documentos podem se referir a entidades especificas.

Exemplos:

```text
PROFESSIONAL_INFO → doctorId = x
PROCEDURE_GUIDANCE → procedureId = y
CLINIC_INFO → unitId = z
```

Modelo recomendado:

```text
entityScope = {
  subjectType,
  subjectId,
  attributes
}
```

Essa abordagem evita dezenas de campos opcionais e permite evoluir escopos sem alterar o contrato conceitual a cada novo tipo de entidade.

Trade-off: metadados estruturados exigem validacao de dominio para impedir escopos malformados.

## Documento estruturado e nao estruturado

O modelo deve suportar conteudo nao estruturado:

```text
PDF
DOCX
texto
FAQ
```

e conteudo estruturado:

```text
catalogo de procedimentos
tabela de precos
politica comercial
```

Nao forcar tudo a virar somente texto. Uma entidade estruturada pode gerar representacao textual para retrieval, mantendo sua estrutura original para decisoes deterministicas.

## Catalogo de procedimentos

A existencia de procedimentos nao deve depender exclusivamente de busca vetorial.

Modelagem recomendada:

```text
PROCEDURE_CATALOG_VERSION
↓
PROCEDURE_CATALOG_ITEM
```

`PROCEDURE_CATALOG_VERSION` e uma especializacao conceitual de `DOCUMENT_VERSION` para `documentType = PROCEDURE_CATALOG`.

`PROCEDURE_CATALOG_ITEM` representa um item estruturado consultavel deterministicamente, ligado a uma versao especifica do catalogo.

Campos conceituais possiveis do item:

```text
id
organizationId
documentVersionId
procedureKey
procedureName
aliases
status
metadata
```

A representacao textual desses itens pode alimentar retrieval, mas a decisao `ENTITY_EXISTENCE + PROCEDURE` deve consultar o catalogo estruturado vigente.

## RETRIEVAL_INDEX_ENTRY

Indexacao deve ser separada do chunk.

```text
CHUNK
↓
RETRIEVAL_INDEX_ENTRY
```

Campos conceituais:

```text
id
organizationId
chunkId
documentId
documentVersionId
embeddingModel
embeddingVersion
indexVersion
indexedAt
indexStatus
```

Objetivos:

- permitir troca de modelo de embedding;
- permitir reindexacao;
- manter conteudo autorizado igual;
- auditar qual versao de indice foi usada.

Este contrato nao escolhe banco vetorial.

## Reindexacao sem nova versao documental

Se o conteudo nao mudou:

```text
reembed / reindex
```

nao cria automaticamente nova `DOCUMENT_VERSION`.

Exemplo:

```text
mesmo conteudo
embedding-model-v1 → embedding-model-v2
```

e mudanca tecnica de indexacao, nao mudanca do conhecimento autorizado.

## RETRIEVAL_EVIDENCE

`RETRIEVAL_EVIDENCE` representa uma evidencia recuperada para uma resposta.

Campos conceituais:

```text
chunkId
documentVersionId
retrievalScore
rerankScore
retrievalMethod
retrievedAt
indexVersion
```

Esse objeto nao precisa ser persistido obrigatoriamente neste modelo, mas o sistema deve conseguir representa-lo na camada de execucao e auditoria.

## AI_RESPONSE, CLAIM e EVIDENCE

Relacao futura:

```text
AI_RESPONSE
↓
CLAIM
↓
EVIDENCE
```

Cada claim factual relevante deve ser capaz de apontar para uma ou mais evidencias.

Exemplo:

```text
Claim:
"A consulta custa R$ 500"

Evidence:
documentVersionId = v2
chunkId = chunk-18
```

Esse desenho sustenta o grounding validator.

## Multi-tenant

Regra geral: entidades operacionais duplicam `organizationId` quando isso reduz risco de vazamento e permite consulta isolada.

Entidades que devem possuir `organizationId` diretamente:

```text
DOCUMENT
DOCUMENT_VERSION
CHUNK
RETRIEVAL_INDEX_ENTRY
RETRIEVAL_EVIDENCE
PROCEDURE_CATALOG_ITEM
```

`AI_RESPONSE` e `CLAIM`, quando forem modeladas, tambem devem possuir ou derivar inequivocamente `organizationId` do atendimento.

Cross-org relationship e invalido.

Exemplo proibido:

```text
chunk.organizationId = A
documentVersion.organizationId = B
```

## Invariantes conceituais

```text
DOCUMENT.organizationId deve ser valido.
DOCUMENT.organizationId + DOCUMENT.canonicalKey identifica um documento logico.
DOCUMENT_VERSION.documentId deve pertencer a mesma organizationId.
DOCUMENT_VERSION.organizationId deve corresponder ao DOCUMENT.organizationId.
CHUNK.documentVersionId deve pertencer a mesma organizationId.
CHUNK.documentId deve corresponder ao documentId da DOCUMENT_VERSION.
RETRIEVAL_INDEX_ENTRY.chunkId deve pertencer a mesma organizationId.
supersedesVersionId deve apontar para versao do mesmo documentId.
uma versao nao pode superseder a si mesma.
```

Para um mesmo `organizationId + documentId`, nao deve haver duas versoes substitutivas simultaneamente vigentes como fonte principal do mesmo documento logico.

Documentos complementares podem coexistir como documentos logicos diferentes, nao como versoes concorrentes do mesmo documento.

## Elegibilidade para retrieval

Conceito derivado:

```text
isRetrievalEligible
```

Regra conceitual:

```text
retrievalEligible =
    documentVersion.status == PUBLISHED
    AND documentVersion.organizationId == activeOrganization
    AND documentVersion.effectiveFrom <= now
    AND (documentVersion.effectiveUntil == null OR documentVersion.effectiveUntil >= now)
    AND documentVersion.processingValid == true
    AND chunk.organizationId == activeOrganization
    AND chunk.documentVersionId == documentVersion.id
```

Para `CLOSED_WORLD`, tambem deve existir:

```text
documentVersion.knowledgeMode == CLOSED_WORLD
AND documentVersion.closedWorldCompletenessApproved == true
```

`PUBLISHED` com `effectiveFrom` futuro nao e verdade atual.

## Soft delete

Comportamento padrao:

```text
INACTIVE
```

`INACTIVE` significa retirado de uso, preservando historico e auditoria.

`DELETED`, se existir futuramente, deve significar remocao permanente ou anonimizada sob regra especifica. Nao deve ser o caminho normal para substituir conhecimento.

## Dados sensiveis

```text
knowledge base != patient memory
```

A base documental deve armazenar conhecimento autorizado da clinica, nao historico individual de pacientes.

Dados conversacionais e memoria de paciente pertencem a outro dominio e nao devem ser misturados ao modelo documental de conhecimento.
