# Overview — ai-customer-service

A feature `ai-customer-service` especifica uma IA de atendimento comercial para clinicas, inicialmente via WhatsApp.

O objetivo e responder perguntas factuais somente com suporte de fontes autorizadas, encaminhando para atendimento humano quando a informacao necessaria nao estiver disponivel ou suficientemente validada.

Documentos da feature:

- `spec.md`: documento principal no padrao ONP Spec-Driven.
- `product-rules.md`: regras de produto e comportamento permitido no atendimento.
- `rag-contract.md`: contrato de fontes, RAG, `CLOSED_WORLD`, `OPEN_WORLD` e grounding.
- `ingestion-contract.md`: contrato de ingestao, aprovacao, publicacao, versionamento e proveniencia documental.
- `data-model.md`: modelo conceitual de documentos, versoes, chunks, indexacao, evidencias e claims.
- `chunking-contract.md`: estrategia de chunking semantico, preservacao de contexto e qualidade dos chunks.
- `acceptance-criteria.md`: criterios de aceite detalhados.
- `tasks.md`: tarefas futuras de implementacao.
