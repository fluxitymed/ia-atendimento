# Chunking Contract — ai-customer-service

## Objetivo

Este contrato define a estrategia conceitual para transformar documentos autorizados em unidades recuperaveis sem destruir relacoes semanticas importantes.

Chunking e uma transformacao tecnica sobre conteudo autorizado. Ele nao autoriza conhecimento, nao resolve conflitos e nao substitui versionamento, publicacao, grounding ou catalogo deterministico.

## Principio central

```text
semantic integrity > fixed size
```

O sistema nao deve adotar como regra principal cortar a cada N caracteres ou a cada N tokens com overlap fixo.

Tamanho pode ser limite tecnico futuro, mas nunca deve ser o unico criterio para definir fronteiras.

Um chunk bom representa uma unidade que pode ser recuperada e interpretada corretamente fora do documento completo.

## SEMANTIC_ATOMIC_UNIT

```text
SEMANTIC_ATOMIC_UNIT
```

e o menor bloco que preserva uma afirmacao completa e corretamente contextualizada.

Exemplo:

```text
Procedimento: Consulta dermatologica
Profissional: Dra. Ana
Valor: R$ 500
Pagamento: PIX ou cartao
Retorno: incluso em ate 30 dias
```

Essas informacoes possuem relacao. O chunking nao deve separar `Valor: R$ 500` de modo que a entidade, profissional, modalidade ou condicao fiquem ambiguos.

## SELF_CONTAINED

Sempre que possivel, um chunk deve ser:

```text
SELF_CONTAINED
```

Ou seja, o trecho recuperado carrega o contexto minimo necessario.

Ruim:

```text
O valor e R$ 500.
```

Melhor:

```text
Consulta com Dra. Ana:
valor da consulta: R$ 500.
```

Esse enriquecimento contextual nao pode inventar conteudo. Ele pode apenas carregar para o chunk contexto ja presente na estrutura ancestral ou na mesma unidade semantica.

## Context inheritance

Chunks podem herdar contexto estrutural de headings, tabelas, listas e escopos ancestrais.

Exemplo de origem:

```text
# Dra. Ana

## Consulta

Valor: R$ 500
Retorno: 30 dias
```

Representacao normalizada permitida:

```text
Profissional: Dra. Ana
Servico: Consulta
Valor: R$ 500
Retorno incluso em ate 30 dias
```

Conceito planejado:

```text
inheritedContext
```

`inheritedContext` deve ser derivado deterministicamente da estrutura do documento e nunca adicionar informacao inexistente.

## Section path

Todo chunk deve preservar ou derivar `CHUNK.sectionPath`.

Exemplo:

```text
Clinica
→ Profissionais
→ Dra. Ana
→ Consulta
→ Valores
```

`sectionPath` apoia proveniencia, reranking, debugging, grounding e auditoria.

## Estrategias por documentType

Nao existe estrategia universal para todos os documentos.

### PROCEDURE_CATALOG

`PROCEDURE_CATALOG` possui natureza estruturada.

Existencia de procedimentos deve ser consultada deterministicamente por:

```text
PROCEDURE_CATALOG_ITEM
```

e nao por ausencia de chunk ou retrieval.

Representacoes textuais podem ser criadas para perguntas semanticas:

```text
Procedimento oferecido: Rinoplastia.
Categoria: Cirurgia facial.
```

Mas presenca ou ausencia oficial continua vindo da estrutura deterministica da versao vigente e completa.

### PRICING

Preco nunca deve perder associacao com:

- procedimento;
- servico;
- profissional;
- unidade;
- modalidade;
- condicao;
- vigencia.

Ruim:

```text
R$ 500
```

Correto conceitualmente:

```text
Consulta presencial com Dra. Ana na unidade Salvador:
valor: R$ 500.
```

Condicoes distintas devem permanecer associadas:

```text
Consulta presencial com Dra. Ana:
valor no PIX: R$ 500.
valor no cartao: R$ 550.
```

### PAYMENT_POLICY

Preservar associacao entre forma de pagamento, limites, parcelamento, excecoes e procedimentos aos quais a regra se aplica.

Regra e excecao diretamente ligada nao devem ficar em chunks independentes sem contexto compartilhado.

### PROFESSIONAL_INFO

Todo chunk deve identificar inequivocamente o profissional.

Exemplo:

```text
Profissional: Dr. Joao Silva
Especialidade: dermatologia
Atende na unidade: Salvador
```

Nao criar chunk contendo atributos sem indicar a qual profissional pertencem.

### PROCEDURE_GUIDANCE

Orientacoes devem preservar:

- procedimento;
- momento;
- orientacao;
- condicao;
- excecao.

Ruim:

```text
Evitar atividade fisica por 7 dias.
```

Correto:

```text
Apos procedimento X:
evitar atividade fisica por 7 dias.
```

### FAQ

Pergunta e resposta relacionadas devem permanecer juntas.

```text
Pergunta: Preciso de encaminhamento?
Resposta: ...
```

Se a resposta depender de contexto especifico, o chunk deve preservar esse contexto.

### CLINIC_INFO

Preservar associacao com unidade quando houver multiplas unidades.

Ruim:

```text
Horario: 08h as 18h.
```

Correto:

```text
Unidade Salvador:
horario administrativo: 08h as 18h.
```

### COMMERCIAL_POLICY

Regra e excecoes devem permanecer juntas quando a excecao modifica diretamente a regra.

Nao criar retrieval em que apenas a regra geral seja recuperavel enquanto a excecao relacionada fica desconectada.

## Tabelas

Tabelas precisam de tratamento estruturado.

Nao transformar cegamente uma tabela em texto corrido.

Exemplo:

| Procedimento | Profissional | Valor |
|---|---|---|
| Consulta | Dra. Ana | R$ 500 |
| Consulta | Dr. Joao | R$ 600 |

Cada linha pode virar uma unidade semantica:

```text
Procedimento: Consulta
Profissional: Dra. Ana
Valor: R$ 500
```

e:

```text
Procedimento: Consulta
Profissional: Dr. Joao
Valor: R$ 600
```

Cabecalhos de tabela devem ser herdados pelas celulas/linhas. O chunk deve manter referencia a tabela, documento, secao, linha e versao quando tecnicamente aplicavel.

## Listas

Listas devem preservar heading e contexto pai.

Origem:

```text
Procedimentos realizados:

- Botox
- Preenchimento
- Bioestimulador
```

Chunk ruim:

```text
Botox
```

Chunk normalizado permitido:

```text
Procedimento oferecido pela clinica: Botox.
```

Somente quando essa transformacao for fiel ao conteudo original e ao contexto ancestral.

## Negacao e qualifiers

Chunks devem preservar palavras e estruturas negativas.

Exemplo:

```text
O procedimento NAO e realizado em gestantes.
```

Nao pode virar:

```text
procedimento realizado em gestantes
```

Futuros testes devem cobrir pelo menos:

- nao;
- nunca;
- exceto;
- somente;
- apenas;
- contraindicado;
- nao incluso;
- nao disponivel.

## Regras, excecoes e condicoes

Regra e excecao semanticamente ligadas devem permanecer recuperaveis com contexto suficiente.

Exemplo:

```text
Parcelamento permitido em ate 6x.
Exceto procedimentos abaixo de R$ 300.
```

Um chunk contendo apenas:

```text
Parcelamento permitido em ate 6x.
```

pode ser perigoso.

Conceito:

```text
RULE + EXCEPTION
```

deve permanecer unido ou mutuamente referenciavel quando a excecao modifica diretamente a regra.

## Referencias anaforicas

Evitar chunks dependentes de expressoes sem antecedente:

- ele;
- ela;
- esse procedimento;
- esse valor;
- nessa condicao;
- o profissional;
- a unidade acima.

Quando possivel, a normalizacao pode substituir a referencia pelo antecedente explicito, desde que isso seja deterministicamente derivavel do documento.

Exemplo:

```text
Botox

Ele pode ser realizado...
```

pode virar:

```text
Botox pode ser realizado...
```

Nao usar LLM livre para inventar resolucao de referencia.

## Tamanho maximo e minimo

Limites futuros de tokens, caracteres, embedding ou contexto sao restricoes secundarias.

Quando uma unidade semantica exceder limite tecnico, aplicar divisao hierarquica:

```text
document
→ section
→ subsection
→ semantic blocks
```

Nunca cortar arbitrariamente no meio de frase, item de regra, excecao, linha de tabela, pergunta/resposta ou entidade + atributo.

Chunks excessivamente pequenos devem, quando semanticamente correto, herdar contexto ou ser agrupados com blocos relacionados.

Nao definir numero definitivo de tokens nesta tarefa.

## Overlap

```text
overlap != semantic integrity
```

Overlap fixo nao e solucao principal para perda de contexto.

Overlap tecnico pode existir futuramente, mas duplicar N tokens nao garante que entidade, condicao e excecao permanecam corretamente associadas.

## Parent-child retrieval

O modelo deve permitir chunking hierarquico.

Exemplo:

```text
PARENT: Procedimento Botox
CHILD 1: Indicacoes
CHILD 2: Preparacao
CHILD 3: Pos-procedimento
```

Um child especifico pode ser recuperado junto com contexto do parent quando necessario.

Campo conceitual:

```text
parentChunkId
```

Nao implementar nesta tarefa.

## semanticType

`CHUNK.semanticType` ajuda retrieval, filtros, reranking e grounding.

Exemplos iniciais:

```text
PRICE
PAYMENT_RULE
PROCEDURE_DESCRIPTION
PREPARATION
POST_PROCEDURE_GUIDANCE
FAQ
PROFESSIONAL_PROFILE
ADDRESS
POLICY
EXCEPTION
CATALOG_ITEM
```

Nao fechar enum definitivo ainda.

## Metadados estruturados do chunk

Metadados podem incluir, quando aplicavel:

```text
procedureId
professionalId
unitId
subjectType
subjectId
documentType
semanticType
sectionPath
```

Diferenca:

- metadado necessario para filtro deve ser estruturado;
- informacao apenas textual pode permanecer no conteudo do chunk.

Nao duplicar indiscriminadamente todos os campos.

## Deterministico x LLM

Parsing e chunking estrutural devem ser deterministicos sempre que o formato fornecer estrutura suficiente.

Exemplos:

- headings;
- paragraphs;
- tables;
- lists;
- FAQ pairs;
- JSON estruturado.

LLM pode auxiliar futuramente em casos complexos, mas nunca pode:

- inventar conteudo;
- completar lacunas;
- modificar valores;
- reinterpretar regras;
- criar condicoes ausentes.

## Fidelidade

```text
normalizedChunkMeaning == sourceMeaning
```

Normalizacao pode:

- expandir headings ancestrais;
- resolver referencias estruturais inequivocas;
- adicionar labels;
- reorganizar formato.

Nao pode alterar significado factual.

Exemplo permitido:

```text
500
```

dentro da coluna `Valor` da linha `Consulta / Dra. Ana` pode virar:

```text
Valor da consulta com Dra. Ana: R$ 500.
```

desde que todos os dados venham inequivocamente da mesma linha/tabela.

## Source span

Planejar rastreabilidade ate a posicao original:

```text
sourcePage
sourceSection
sourceStartOffset
sourceEndOffset
sourceTable
sourceRow
```

Nem todo formato tera todos os campos.

Objetivo:

```text
chunk
→ trecho exato do documento original
```

## Deduplicacao

O sistema deve ser capaz de identificar chunks identicos ou altamente semelhantes para reduzir ruido, identificar conflitos e evitar sobrepeso artificial no retrieval.

Duplicacao nao significa automaticamente erro.

## Conflitos

Se duas fontes dizem:

```text
Consulta = R$ 500
```

e:

```text
Consulta = R$ 600
```

o chunker nao escolhe uma.

Conflitos pertencem a versionamento, publicacao, retrieval e grounding. Chunking deve preservar fielmente fontes e proveniencias.

## Vigencia

Chunks carregam ou derivam vigencia da `DOCUMENT_VERSION`.

Nao incorporar data de vigencia como se texto no chunk fosse suficiente para autorizar retrieval.

Elegibilidade continua determinada pela versao documental.

## CLOSED_WORLD

Para `PROCEDURE_CATALOG`:

```text
absence detection != vector retrieval
```

A resposta "Nao realizamos esse procedimento" nao pode acontecer porque nenhum chunk semelhante foi encontrado.

Ela somente pode acontecer apos consulta deterministica a versao vigente e completa do catalogo fechado.

Chunking textual do catalogo e complementar.

## Exemplos perigosos

### Condicao transformada em regra geral

Documento:

```text
Consulta com Dra. Ana

Valor padrao: R$ 500.

Pacientes do programa X pagam R$ 400.
```

Chunk perigoso:

```text
Consulta com Dra. Ana custa R$ 400.
```

porque transformou condicao especifica em regra geral.

Chunks corretos:

```text
Consulta com Dra. Ana:
valor padrao: R$ 500.
```

e:

```text
Consulta com Dra. Ana:
para pacientes do programa X, o valor e R$ 400.
```

### Excecao removida

Documento:

```text
O procedimento pode ser realizado a partir dos 18 anos,
exceto quando houver indicacao medica especifica.
```

Nao separar em:

```text
Pode ser realizado a partir dos 18 anos.
```

ignorando a excecao relevante.

## Validacao futura de qualidade

Planejar validacao futura do resultado de chunking.

Verificacoes possiveis:

- chunk tem proveniencia?
- chunk identifica entidade quando necessario?
- chunk perdeu negacao?
- chunk perdeu condicao?
- chunk perdeu excecao?
- chunk esta vazio?
- chunk e pequeno demais para ter significado?
- chunk excede limite?
- chunk contem referencia sem antecedente?

## Versionamento tecnico do chunking

Planejar:

```text
chunkingStrategy
chunkingVersion
```

Exemplo:

```text
strategy-v1
→ strategy-v2
```

Reprocessar documentos por nova estrategia de chunking nao altera automaticamente a versao do conhecimento quando o conteudo original nao mudou.

Chunking e transformacao tecnica.

## Relacao com indexacao

Fluxo conceitual:

```text
DOCUMENT_VERSION
↓
normalized content
↓
CHUNKING STRATEGY
↓
CHUNKS
↓
RETRIEVAL INDEX
```

Geracao de chunks nao deve ser acoplada ao modelo especifico de embedding.

Os mesmos chunks podem, em principio, ser indexados por diferentes versoes ou modelos.
