# Tasks — ai-customer-service

## T-001 — Implementar classificacao de ausencia de informacao para handoff [concluida]

- Refs: AC-001, AC-005, AC-006, AC-007
- Arquivos: src/ai-customer-service/domain/constants.js, src/ai-customer-service/domain/handoff-policy.js, src/ai-customer-service/domain/index.js, test/ai-customer-service/handoff-policy.test.js

Implementar a classificacao interna `HUMAN_HANDOFF_REQUIRED` quando informacao factual relevante nao estiver suficientemente suportada por fonte autorizada.

Preservar o contexto da conversa para transferencia humana e exigir mensagem de transicao configuravel pela clinica, sem expor termos tecnicos ou ausencia de informacao ao paciente.

## T-002 — Definir contrato de ingestao documental da IA [concluida]

- Refs: US-005
- Arquivos: .spec/features/ai-customer-service/ingestion-contract.md, .spec/features/ai-customer-service/spec.md, .spec/features/ai-customer-service/acceptance-criteria.md, .spec/features/ai-customer-service/rag-contract.md, .spec/features/ai-customer-service/tasks.md

Definir o contrato de entrada, validacao, processamento, aprovacao, publicacao, versionamento, vigencia, proveniencia e protecao contra conteudo nao autorizado dos documentos que futuramente poderao fundamentar respostas da IA.

## T-003 — Definir modelo de dados documental e de proveniencia [concluida]

- Refs: US-006
- Arquivos: .spec/features/ai-customer-service/data-model.md, .spec/features/ai-customer-service/spec.md, .spec/features/ai-customer-service/acceptance-criteria.md, .spec/features/ai-customer-service/ingestion-contract.md, .spec/features/ai-customer-service/tasks.md

Definir o modelo conceitual de `DOCUMENT`, `DOCUMENT_VERSION`, `CHUNK`, indexacao, evidencia, claims, isolamento multi-tenant, `CLOSED_WORLD` versionado e catalogo estruturado, sem criar schema SQL ou codigo funcional.

## T-004 — Definir estrategia de chunking semantico e preservacao de contexto [concluida]

- Refs: US-007
- Arquivos: .spec/features/ai-customer-service/chunking-contract.md, .spec/features/ai-customer-service/spec.md, .spec/features/ai-customer-service/acceptance-criteria.md, .spec/features/ai-customer-service/data-model.md, .spec/features/ai-customer-service/rag-contract.md, .spec/features/ai-customer-service/tasks.md

Definir contrato de chunking orientado por integridade semantica, heranca de contexto, estrategia por `documentType`, preservacao de regras/excecoes/negacoes, parent-child chunks, source span e versionamento tecnico, sem implementar chunker.

## T-005 — Implementar fundacao deterministica e testes das invariantes da IA [concluida]

- Refs: AC-002, AC-003, AC-004, AC-008, AC-009, AC-010, AC-011, AC-013, AC-017, AC-018, AC-019, AC-021, AC-022, AC-030
- Arquivos: src/ai-customer-service/domain/constants.js, src/ai-customer-service/domain/document-lifecycle.js, src/ai-customer-service/domain/retrieval-eligibility.js, src/ai-customer-service/domain/organization-guards.js, src/ai-customer-service/domain/procedure-catalog-policy.js, src/ai-customer-service/domain/version-authority.js, src/ai-customer-service/domain/index.js, test/ai-customer-service/domain.test.js

Implementar regras puras e deterministicas para lifecycle documental, elegibilidade de retrieval, isolamento por organizacao, supersessao de versoes, autoridade de chunks, autorizacao `CLOSED_WORLD`, decisao de existencia em `PROCEDURE_CATALOG` e distincao entre `ENTITY_EXISTENCE` e `ENTITY_ATTRIBUTE`, com testes reais anotados.

## T-006 — Implementar lifecycle e publicacao documental [concluida]

- Refs: AC-008, AC-010, AC-011, AC-014
- Arquivos: src/ai-customer-service/domain/constants.js, src/ai-customer-service/domain/document-lifecycle.js, src/ai-customer-service/domain/retrieval-eligibility.js, src/ai-customer-service/domain/version-authority.js, test/ai-customer-service/domain.test.js

Implementar estados documentais, bloqueio de documentos nao publicados, versionamento substitutivo, vigencia e bloqueio de publicacao quando houver falha de processamento.

## T-007 — Implementar isolamento e proveniencia de retrieval documental [concluida]

- Refs: AC-009, AC-012
- Arquivos: src/ai-customer-service/domain/constants.js, src/ai-customer-service/domain/index.js, src/ai-customer-service/domain/organization-guards.js, src/ai-customer-service/domain/provenance.js, src/ai-customer-service/domain/retrieval-eligibility.js, test/ai-customer-service/domain.test.js

Garantir que documentos e chunks publicados carreguem `organizationId` valido e proveniencia completa ate documento, versao, organizacao, secao, publicacao e aprovacao.

## T-008 — Implementar protecao contra prompt injection documental [concluida]

- Refs: AC-015
- Arquivos: src/ai-customer-service/domain/document-content-policy.js, src/ai-customer-service/domain/index.js, test/ai-customer-service/domain.test.js

Tratar conteudo documental como dado, impedindo que instrucoes dentro de documentos alterem system prompt, regras do agente, permissoes de tools, politicas, grounding ou handoff.

## T-009 — Implementar distincao entre existencia e atributos da entidade [concluida]

- Refs: AC-003, AC-004
- Arquivos: src/ai-customer-service/domain/intent-classifier.js, src/ai-customer-service/domain/procedure-catalog-policy.js, src/ai-customer-service/domain/index.js, test/ai-customer-service/domain.test.js

Classificar perguntas como `ENTITY_EXISTENCE` ou `ENTITY_ATTRIBUTE` antes de decidir se ausencia pode sustentar resposta negativa.

## T-010 — Implementar modelo documental, versionamento e elegibilidade [concluida]

- Refs: AC-016, AC-019, AC-020, AC-022
- Arquivos: src/ai-customer-service/domain/document-model.js, src/ai-customer-service/domain/retrieval-eligibility.js, src/ai-customer-service/domain/version-authority.js, src/ai-customer-service/domain/index.js, test/ai-customer-service/domain.test.js

Implementar entidades documentais, versoes, elegibilidade derivada para retrieval, reindexacao desacoplada e garantia de versao substitutiva unica como verdade atual.

## T-011 — Implementar proveniencia, isolamento e evidencias de retrieval [concluida]

- Refs: AC-017, AC-018
- Arquivos: src/ai-customer-service/domain/organization-guards.js, src/ai-customer-service/domain/provenance.js, src/ai-customer-service/domain/index.js, test/ai-customer-service/domain.test.js

Implementar rastreabilidade de chunk ate versao, documento e organizacao, bloqueando relacionamentos cross-organization entre documento, versao, chunk, indice e evidencia.

## T-012 — Implementar closed world versionado e catalogo estruturado [concluida]

- Refs: AC-013, AC-021
- Arquivos: src/ai-customer-service/domain/procedure-catalog-policy.js, src/ai-customer-service/domain/retrieval-eligibility.js, src/ai-customer-service/domain/index.js, test/ai-customer-service/domain.test.js

Implementar autorizacao `CLOSED_WORLD` por versao documental completa e catalogo de procedimentos estruturado para decisoes deterministicas de existencia.

## T-013 — Separar base documental de memoria de paciente [concluida]

- Refs: AC-023
- Arquivos: src/ai-customer-service/domain/constants.js, src/ai-customer-service/domain/document-knowledge-policy.js, src/ai-customer-service/domain/index.js, test/ai-customer-service/domain.test.js

Garantir que o dominio documental armazene conhecimento autorizado da clinica, sem misturar historico individual ou memoria de pacientes.

## T-014 — Atualizar grounding validator [concluida]

- Refs: AC-002, AC-003, AC-004, AC-005, AC-024, AC-025, AC-028, AC-031
- Arquivos: src/ai-customer-service/domain/constants.js, src/ai-customer-service/domain/grounding-validator.js, src/ai-customer-service/domain/handoff-policy.js, src/ai-customer-service/domain/procedure-catalog-policy.js, src/ai-customer-service/domain/provenance.js, src/ai-customer-service/domain/index.js, test/ai-customer-service/grounding-validator.test.js

Garantir que afirmacoes negativas so sejam aprovadas por ausencia quando vierem de fonte `CLOSED_WORLD` autorizada para aquele escopo, e que respostas factuais nao sejam validadas por chunks que perderam contexto, negacao, condicao, excecao ou proveniencia.

## T-015 — Implementar chunking semantico por tipo documental [concluida]

- Refs: AC-024, AC-026, AC-027, AC-029
- Arquivos: src/ai-customer-service/domain/semantic-chunking.js, src/ai-customer-service/domain/index.js, test/ai-customer-service/chunking.test.js

Implementar chunking por `documentType`, preservando unidades semanticas, FAQ, tabelas, listas, contexto ancestral e `sectionPath`.

## T-016 — Implementar preservacao de regras, excecoes, negacoes e qualifiers [concluida]

- Refs: AC-025, AC-028
- Arquivos: src/ai-customer-service/domain/semantic-chunking.js, test/ai-customer-service/chunking.test.js

Garantir que normalizacao e chunking nao removam ou alterem negacoes, condicoes, qualifiers, regras e excecoes semanticamente ligadas.

## T-017 — Implementar parent-child chunks, source span e versionamento tecnico [concluida]

- Refs: AC-031, AC-032
- Arquivos: src/ai-customer-service/domain/semantic-chunking.js, src/ai-customer-service/domain/grounding-validator.js, test/ai-customer-service/chunking.test.js, test/ai-customer-service/grounding-validator.test.js

Implementar `parentChunkId`, source span quando aplicavel, `chunkingStrategy` e `chunkingVersion`, sem criar nova `DOCUMENT_VERSION` quando apenas a estrategia tecnica mudar.

## T-018 — Garantir que catalogo fechado nao dependa de retrieval vetorial [concluida]

- Refs: AC-030
- Arquivos: src/ai-customer-service/domain/procedure-catalog-policy.js, src/ai-customer-service/domain/grounding-validator.js, test/ai-customer-service/domain.test.js, test/ai-customer-service/grounding-validator.test.js

Garantir que `NOT_OFFERED` para `PROCEDURE_CATALOG` venha apenas de consulta deterministica a versao vigente e completa do catalogo fechado, nunca de ausencia de chunk ou resultado vetorial.
