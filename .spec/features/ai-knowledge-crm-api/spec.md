# API privada de conhecimento para CRM

> feature: ai-knowledge-crm-api
> status: em-implementacao

## Contexto

Expor o núcleo `KnowledgeAdmin` por HTTP ao backend CRM, preservando CLI e isolamento multi-tenant.

## Histórias

### US-118 — Operar conhecimento no CRM com segurança

Como administrador autorizado no CRM, quero revisar e publicar documentos por uma API interna, para gerir o RAG da organização sem acesso direto ao banco da IA.

#### AC-513 — Token privado obrigatório

- **Dado** token ausente, inválido ou credencial de dispatch
- **Quando** qualquer rota de conhecimento é chamada
- **Então** 401 sem consultar banco nem ecoar credenciais.

#### AC-514 — Tenant explícito e ativo

- **Dado** organizationId ausente, inválido, inexistente ou inativo
- **Quando** qualquer operação é solicitada
- **Então** falha fechada antes de escrever ou gerar embeddings.

#### AC-515 — Dry-run estruturado

- **Dado** Markdown UTF-8 e nome lógico válidos
- **Quando** CRM faz dry-run
- **Então** retorna hash, status, versões, chunks estimados e resumo sem escrita nem conteúdo.

#### AC-516 — Ingestão pendente

- **Dado** fonte nova
- **Quando** CRM faz ingest
- **Então** o core cria documentos, versão REVIEW_REQUIRED, chunks e índices do tenant.

#### AC-517 — Repetição idempotente

- **Dado** fonte idêntica já ingerida
- **Quando** CRM repete ingest
- **Então** retorna mesmos IDs sem novo embedding ou versão.

#### AC-518 — Validação humana

- **Dado** versão pendente e ator identificado
- **Quando** CRM valida o versionId
- **Então** integridade é verificada e fica APPROVED sem publicar.

#### AC-519 — Publicação atômica

- **Dado** versão aprovada e uma anterior PUBLISHED
- **Quando** CRM publica o versionId
- **Então** nova fica PUBLISHED, anterior SUPERSEDED no mesmo commit.

#### AC-520 — Isolamento de leitura

- **Dado** documento de A e requisição de B
- **Quando** CRM lista ou consulta detalhe/versões
- **Então** recurso de A não aparece e lookup direto retorna 404.

#### AC-521 — Isolamento de mutação

- **Dado** versionId de A e organizationId de B
- **Quando** CRM valida ou publica
- **Então** 404 sem revelar o recurso estrangeiro.

#### AC-522 — Concorrência e versão obsoleta

- **Dado** dois publicadores ou nova revisão concorrente
- **Quando** CRM publica ou repete publicação
- **Então** lock serializa; retry é idempotente; versão obsoleta falha.

#### AC-523 — Fonte inválida e limites

- **Dado** arquivo vazio, sintaxe não suportada, tamanho/tipo fora do limite
- **Quando** CRM envia documento
- **Então** erro controlado sem escrita parcial.

#### AC-524 — Relatório sem segredos

- **Dado** conteúdo, embedding ou exceção com credenciais
- **Quando** API responde ou audita
- **Então** resposta e logs não incluem conteúdo integral, vetor ou segredo.

#### AC-525 — Listagem operacional

- **Dado** documento com publicação e revisão pendente
- **Quando** CRM lista documentos, detalhe e versões
- **Então** vê status, versões, datas e hash sem vetor.

#### AC-526 — Revisão pontual

- **Dado** documento e versão do tenant
- **Quando** CRM pede o endpoint de revisão
- **Então** recebe chunks daquela versão somente sob autenticação e escopo.

#### AC-527 — Smoke privado

- **Dado** versão publicada e consulta
- **Quando** CRM pede smoke
- **Então** runtime vigente é testado sem texto de evidência na resposta.

#### AC-528 — Auditoria correlacionada

- **Dado** requisição autenticada com correlationId e actor
- **Quando** há sucesso ou erro
- **Então** evento seguro registra operação, tenant, IDs, ator, correlação, horário e resultado.

#### AC-529 — Compatibilidade CLI e core único

- **Dado** CLI legado e API disponíveis
- **Quando** ambos ingerem, validam ou publicam
- **Então** ambos chamam KnowledgeAdmin e CLI mantém seus contratos.

#### AC-530 — HTTP e segurança de entrada

- **Dado** método, rota ou JSON incorreto
- **Quando** servidor recebe requisição
- **Então** retorna 4xx controlado, limita body e não imprime payload.

## Fora de escopo

UI/Backend do CRM, deploy, carga Hartmann, publicação real, autenticação de usuário final na IA.

## Suposições

Nenhuma pendente. O backend CRM já autentica usuários e deve impor membership e papel administrativo antes de usar o token privado; a IA confia no tenant explícito de um cliente de serviço autenticado e ainda verifica o tenant no banco.

## Perguntas em aberto

Nenhuma para esta implementação. Provisionamento do token e integração da UI/Backend CRM são tarefas operacionais futuras descritas no contrato.
