# RAG Contract — ai-customer-service

## Objetivo

O contrato RAG define quais fontes podem sustentar respostas factuais e quando ausencia de informacao pode ou nao ser usada como evidencia negativa.

O atendimento final nunca deve expor ao paciente detalhes internos de busca, recuperacao, chunks, scores, documentos, RAG ou falta de evidencia.

Documentos so podem alimentar retrieval de producao quando respeitarem tambem o `ingestion-contract.md`: conteudo enviado ou processado nao e automaticamente aprovado, e somente conteudo `PUBLISHED`, vigente, autorizado e isolado por organizacao pode ser recuperado.

Chunks tambem devem respeitar o `chunking-contract.md`: retrieval de producao nao deve depender de fragmentos que perderam entidade, atributo, condicao, excecao, negacao, vigencia ou proveniencia.

## Tipos de mundo

Fontes autorizadas devem declarar explicitamente se representam mundo fechado ou mundo aberto.

```text
CLOSED_WORLD
OPEN_WORLD
```

## CLOSED_WORLD

Uma fonte `CLOSED_WORLD` e completa para o escopo explicitamente definido pelo dominio. Dentro desse escopo, ausencia da entidade pode significar inexistencia.

Fonte inicial:

```text
PROCEDURE_CATALOG
```

Escopo inicial:

```text
procedures_catalog
```

Regra:

```text
Se o procedimento nao esta no catalogo ativo, aprovado e completo, o procedimento nao e oferecido.
```

Essa regra vale somente para perguntas de existencia do procedimento.

Para `PROCEDURE_CATALOG`, o documento publicado deve representar explicitamente a lista oficial e completa de procedimentos atualmente oferecidos pela clinica. O sistema nao pode inferir `CLOSED_WORLD` apenas porque um documento parece uma lista.

## OPEN_WORLD

Uma fonte `OPEN_WORLD` nao permite concluir que uma informacao ausente seja falsa.

Exemplos:

```text
pricing
payment_conditions
medical_guidance
preparation
recovery
schedule
professional_information
policies
```

Regra:

```text
Ausencia de informacao em OPEN_WORLD = HUMAN_HANDOFF_REQUIRED
```

## Ausencia de evidencias de retrieval

Nenhum resultado de retrieval, baixa pontuacao ou ausencia de chunks nao sao evidencia de falsidade.

```text
nenhum resultado de retrieval
```

nao significa:

```text
informacao falsa
```

A excecao so existe quando uma fonte estruturada foi explicitamente definida como catalogo completo e fechado para aquele escopo.

Para `PROCEDURE_CATALOG`, ausencia de procedimento nao pode ser determinada por ausencia de chunk ou resultado vetorial semelhante. A decisao deve consultar a estrutura deterministica vigente do catalogo fechado.

## Grounding validator

O grounding validator deve validar afirmacoes negativas de acordo com o tipo de mundo da fonte.

Uma afirmacao negativa como:

```text
A clinica nao realiza rinoplastia.
```

somente pode ser aprovada quando:

- a pergunta foi classificada como `ENTITY_EXISTENCE`;
- `entity_type = PROCEDURE`;
- a fonte consultada foi `PROCEDURE_CATALOG`;
- o catalogo esta ativo, aprovado e marcado como `CLOSED_WORLD`;
- o procedimento nao foi encontrado no catalogo por regra deterministica.

A mesma afirmacao negativa nao pode ser aprovada apenas por ausencia de chunks, ausencia de documentos, score baixo ou falha de retrieval.

## Decisao por tipo de pergunta

### ENTITY_EXISTENCE + PROCEDURE

Consultar `PROCEDURE_CATALOG`.

Se encontrado, continuar atendimento usando fontes autorizadas para eventuais atributos.

Se nao encontrado e o catalogo estiver marcado como `CLOSED_WORLD`, responder `NOT_OFFERED`.

### ENTITY_ATTRIBUTE

Determinar a fonte necessaria para o atributo.

Se a informacao estiver suficientemente suportada, gerar e validar resposta.

Se a informacao nao estiver suficientemente suportada:

```text
HUMAN_HANDOFF_REQUIRED
```

Nao inferir resposta negativa a partir da ausencia.
