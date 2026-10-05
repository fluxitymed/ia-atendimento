# RAG multi-tenant pronto para base Hartmann

> feature: ai-hartmann-knowledge-readiness
> status: implementada

## Contexto

O runtime vivo consulta `document_versions` e `chunks` do Supabase. A Hartmann (organization_id `38002ccb-9edb-4dcb-aacf-76c0b6ca1692`) ainda nao possui documentos publicados. Antes da primeira carga, o retrieval deve recusar dados de outro tenant, versoes nao vigentes e chunks inconsistentes; o grounding deve rejeitar claims sem suporte factual.

## Historias

### US-115 — Recuperar somente conhecimento autorizado da clinica

Como paciente da Hartmann, quero respostas baseadas apenas na base vigente da Hartmann, para nao receber informacoes de outra clinica ou de versoes antigas.

#### AC-494 — Isolamento bidirecional

- **Dado** documentos e chunks da Hartmann e de uma organizacao B
- **Quando** cada organizacao pesquisa o mesmo termo
- **Entao** cada uma recebe apenas seu proprio chunk e cada consulta e escopada por `organization_id`.

#### AC-495 — Estado e processamento validos

- **Dado** versoes rascunho, inativas, invalidas e expiradas
- **Quando** o runtime recupera conhecimento
- **Entao** nenhum chunk dessas versoes entra no contexto.

#### AC-496 — Apenas versao atual

- **Dado** duas versoes publicadas do mesmo documento
- **Quando** ocorre o retrieval
- **Entao** somente a versao vigente de maior `version_number` entra no contexto.

#### AC-497 — Relacionamento documental coerente

- **Dado** um chunk cujo `document_id` difere do documento de sua versao
- **Quando** ocorre o retrieval
- **Entao** o chunk inconsistente e descartado.

#### AC-498 — Organizacao obrigatoria

- **Dado** uma busca sem `organization_id`
- **Quando** o caminho canonico recebe a busca
- **Entao** ele falha fechado antes de consultar o Supabase.

### US-116 — Bloquear fatos nao sustentados

Como paciente, quero que uma afirmacao factual da clinica exija evidencia atual, para evitar informacao inventada ou herdada de cache obsoleto.

#### AC-499 — Grounding com conteudo pertinente

- **Dado** uma resposta factual com evidencia nao relacionada, preco divergente ou apenas chunk antigo em cache
- **Quando** a resposta e validada
- **Entao** ela e recusada; uma afirmacao literalmente sustentada por evidencia atual pode passar.

## Fora de escopo

- Inserir documentos reais, criar credenciais, usar OpenAI real, escrever no Supabase de Production ou fazer deploy.
- Criar nova tabela de chunks ou endpoint publico de ingestao.

## Suposicoes

| ID | Suposicao | Status | Resolucao |
|---|---|---|---|
| ASM-047 | Uma versao publicada de maior `version_number` e a versao atual quando duas publicadas coexistem para o mesmo documento. | confirmada | Coerente com o contrato de substituicao; consulta real nao mostrou documentos Hartmann, e o teste cobre a concorrencia. |

## Perguntas em aberto

| ID | Pergunta | Status | Resposta |
|---|---|---|---|
| Q-009 | A primeira base pode ser publicada sem aprovacao humana registrada? | respondida | Nao. O contrato de ingestao exige aprovador identificado antes de qualquer publicacao; a pessoa sera designada na operacao futura. |
