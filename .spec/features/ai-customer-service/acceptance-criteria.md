# Acceptance Criteria — ai-customer-service

## AC-001 — Informacao desconhecida

Dado que o paciente fez uma pergunta factual relevante sobre clinica, profissional, procedimento, condicao comercial ou atendimento
Quando a informacao necessaria nao estiver disponivel em fonte autorizada
Entao o sistema deve classificar internamente a situacao como `HUMAN_HANDOFF_REQUIRED`
E nao deve expor ao paciente ausencia de informacao, ausencia de evidencia ou detalhes tecnicos de busca.

## AC-002 — Procedimento inexistente

Dado que o paciente perguntou diretamente se a clinica realiza um procedimento
E existe um catalogo de procedimentos completo, ativo, aprovado e marcado como `CLOSED_WORLD`
Quando o procedimento nao estiver cadastrado nesse catalogo
Entao a IA pode informar que a clinica atualmente nao realiza o procedimento.

## AC-003 — Catalogo fechado

Dado que uma resposta negativa depende de ausencia de uma entidade
Quando a fonte consultada nao estiver explicitamente marcada como `CLOSED_WORLD` para aquele escopo
Entao o sistema nao pode usar a ausencia como evidencia negativa
E deve seguir o fluxo de informacao insuficiente.

## AC-004 — Atributos ausentes

Dado que um procedimento existe no catalogo autorizado
Quando o paciente perguntar sobre um atributo do procedimento, como preco, parcelamento, preparo, recuperacao, duracao, disponibilidade ou contraindicações
E esse atributo nao estiver disponivel em fonte autorizada
Entao o sistema deve classificar a situacao como `HUMAN_HANDOFF_REQUIRED`
E nao deve responder com uma negativa inferida.

## AC-005 — Sem linguagem tecnica no atendimento final

Dado que uma resposta sera enviada ao paciente
Quando a resposta for gerada para o atendimento final
Entao ela nao deve mencionar RAG, base, documentos, retrieval, evidencia insuficiente, informacao nao encontrada, score de busca ou falha de busca.

## AC-006 — Handoff com contexto

Dado que o sistema classificou a situacao como `HUMAN_HANDOFF_REQUIRED`
Quando o atendimento for transferido para uma pessoa
Entao o contexto da conversa deve ser preservado para que o humano consiga assumir sem solicitar novamente informacoes ja fornecidas pelo paciente.

## AC-007 — Mensagem de transicao configuravel

Dado que o sistema classificou a situacao como `HUMAN_HANDOFF_REQUIRED`
Quando uma mensagem de transicao for enviada ao paciente
Entao a mensagem deve usar texto autorizado e configuravel pela clinica
E nao deve mencionar limitacoes tecnicas ou ausencia de informacao.

## AC-008 — Documento nao publicado

Dado que um documento esta em qualquer estado diferente de `PUBLISHED`
Quando o retrieval de producao selecionar fontes para uma resposta
Entao esse documento nao pode fundamentar a resposta da IA.

## AC-009 — Isolamento organizacional

Dado que um documento sera publicado ou recuperado em producao
Quando o sistema avaliar sua elegibilidade
Entao o documento deve possuir `organizationId` valido
E somente pode ser recuperado dentro da mesma organizacao.

## AC-010 — Versionamento

Dado que existe uma versao publicada de um documento
Quando uma nova versao substitutiva for publicada
Entao a versao anterior nao pode continuar sendo considerada vigente
E deve permanecer rastreavel para auditoria.

## AC-011 — Vigencia

Dado que um documento possui `effectiveFrom` e/ou `effectiveUntil`
Quando a data atual estiver fora do periodo de vigencia
Entao o documento nao pode fundamentar resposta atual da IA.

## AC-012 — Proveniencia

Dado que um chunk esta disponivel para retrieval de producao
Quando o sistema auditar sua origem
Entao o chunk deve ser rastreavel ao documento, versao, organizacao, secao, publicacao e aprovacao de origem.

## AC-013 — Closed world

Dado que uma fonte sera usada como `CLOSED_WORLD`
Quando o sistema avaliar ausencia de entidade como evidencia negativa
Entao a fonte deve ter sido explicitamente marcada e aprovada como catalogo completo para aquele escopo.

## AC-014 — Falha de processamento

Dado que a extracao, normalizacao, validacao, chunking ou campo obrigatorio de um documento falhou
Quando o sistema avaliar a publicacao desse documento
Entao o documento nao pode ser publicado
E deve permanecer corrigivel ou reprocessavel.

## AC-015 — Prompt injection documental

Dado que um documento contem texto com instrucoes, comandos ou tentativa de prompt injection
Quando o conteudo for processado ou recuperado
Entao esse conteudo deve ser tratado como dado
E nao pode substituir system prompt, regras do agente, permissoes de tools, politicas, grounding ou handoff.

## AC-016 — Documento e versao

Dado que um conhecimento documental possui identidade duradoura e multiplas edicoes possiveis
Quando o modelo conceitual representar esse conhecimento
Entao `DOCUMENT` e `DOCUMENT_VERSION` devem ser entidades distintas
E uploads ou edicoes novas nao devem substituir a identidade logica do documento.

## AC-017 — Proveniencia de chunk

Dado que um chunk esta disponivel para retrieval
Quando sua proveniencia for auditada
Entao ele deve apontar para `DOCUMENT_VERSION`, `DOCUMENT` e `organizationId`.

## AC-018 — Isolamento cross-org

Dado que entidades documentais possuem ou derivam `organizationId`
Quando o sistema validar relacoes entre documento, versao, chunk, indice ou evidencia
Entao relacoes entre organizacoes diferentes devem ser consideradas invalidas.

## AC-019 — Elegibilidade herdada da versao

Dado que um chunk pertence a uma versao documental
Quando o retrieval de producao avaliar esse chunk
Entao ele somente pode participar se a versao estiver publicada, vigente, processada validamente e isolada na organizacao ativa.

## AC-020 — Indexacao desacoplada

Dado que o conteudo autorizado de uma versao documental nao mudou
Quando o sistema executar `reembed` ou `reindex`
Entao a mudanca de indexacao nao deve criar automaticamente nova `DOCUMENT_VERSION`.

## AC-021 — Closed world versionado

Dado que uma fonte sera usada como `CLOSED_WORLD`
Quando o modelo conceitual registrar essa autorizacao
Entao o modo efetivo e a aprovacao de completude devem pertencer a `DOCUMENT_VERSION`.

## AC-022 — Versao unica vigente

Dado que duas versoes pertencem ao mesmo documento logico e uma substitui a outra
Quando a nova versao se tornar vigente
Entao a versao substituida nao pode concorrer como fonte atual equivalente.

## AC-023 — Conhecimento nao e memoria de paciente

Dado que a IA atendera pacientes
Quando o modelo documental armazenar conhecimento para retrieval
Entao ele deve armazenar conhecimento autorizado da clinica
E nao historico individual ou memoria de pacientes.

## AC-024 — Integridade semantica

Dado que um documento autorizado contem uma entidade e seus atributos relacionados
Quando o conteudo for transformado em chunks
Entao o chunk nao pode separar entidade de atributo de forma que altere ou torne ambiguo o significado.

## AC-025 — Regra e excecao

Dado que uma excecao modifica diretamente uma regra
Quando o chunking produzir unidades recuperaveis
Entao a excecao deve permanecer recuperavel junto do contexto da regra.

## AC-026 — FAQ

Dado que uma FAQ contem pergunta e resposta relacionadas
Quando o chunking processar essa FAQ
Entao pergunta e resposta nao podem ser separadas de forma ambigua.

## AC-027 — Tabelas

Dado que uma informacao vem de linha ou celula de tabela
Quando ela for normalizada em chunk
Entao o chunk deve herdar os cabecalhos necessarios para interpretar o valor.

## AC-028 — Negacao

Dado que o texto original contem negacao, condicao ou qualifier como nao, exceto, somente ou contraindicado
Quando o conteudo for normalizado ou chunkado
Entao a negacao, condicao ou qualifier nao pode ser removido nem alterado.

## AC-029 — Contexto ancestral

Dado que uma informacao depende de heading, tabela, lista ou escopo ancestral
Quando o chunk for enriquecido com contexto
Entao o contexto herdado deve vir apenas de informacao presente e inequivoca no documento.

## AC-030 — Catalogo fechado

Dado que o paciente pergunta se a clinica realiza um procedimento
Quando o sistema avaliar ausencia no `PROCEDURE_CATALOG`
Entao a decisao nao pode usar ausencia de chunk ou retrieval vetorial como evidencia de `NOT_OFFERED`.

## AC-031 — Proveniencia de chunk

Dado que um chunk foi criado a partir de documento autorizado
Quando sua origem for auditada
Entao ele deve apontar para documento, versao, organizacao, sectionPath e source span quando tecnicamente aplicavel.

## AC-032 — Versionamento tecnico de chunking

Dado que o conteudo autorizado de uma versao documental nao mudou
Quando o sistema aplicar nova `chunkingStrategy` ou `chunkingVersion`
Entao essa mudanca tecnica nao deve criar automaticamente nova `DOCUMENT_VERSION`.
