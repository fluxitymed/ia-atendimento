# RAG multi-tenant pronto para base Hartmann

> feature: ai-hartmann-knowledge-readiness
> status: implementada

## Contexto

O runtime vivo consulta `document_versions` e `chunks` do Supabase. A Hartmann (organization_id `38002ccb-9edb-4dcb-aacf-76c0b6ca1692`) possui documentos publicados. O retrieval deve recusar dados de outro tenant, versoes nao vigentes e chunks inconsistentes; o grounding deve rejeitar claims sem suporte factual. No incidente de 2026-10-08, a busca por Botox recuperou duas ocorrencias, mas o dispatch nao persistiu o resultado do modelo nem a causa final do HANDOFF. A causa exata desse resultado permanece nao comprovada.

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
- **E** uma modalidade descrita como `sem reposicao` nao nega a oferta de Botox nem bloqueia outra modalidade com preco sustentado; uma negativa real como `nao oferece Botox` continua bloqueando afirmacoes positivas.
- **E** perguntas comerciais por preco de procedimento recuperam tambem a regra publicada de orcamento final; perguntas por parcelamento recuperam a politica publicada mesmo quando o paciente usa o verbo `parcelar`.

### US-120 — Explicar a decisao do dispatch sem expor dados

Como operador da IA, quero correlacionar cada decisao do dispatch CRM com as etapas do runtime, para distinguir falta de evidencia, rejeicao no grounding, resposta fundamentada e silencio intencional sem acessar conteudo do paciente.

#### AC-533 — Diagnostico terminal por correlationId

- **Dado** dispatches controlados que terminam em `SEND_MESSAGE`, `HANDOFF` e `NO_ACTION`
- **Quando** o processador devolve cada acao
- **Entao** um evento estruturado registra `correlationId`, `organizationId`, `conversationId`, acao, origem da decisao (`MODEL`, `DETERMINISTIC_RULE`, `GROUNDING`, `FALLBACK`, `ERROR_POLICY` ou `UNKNOWN`), codigo estavel do motivo, estado do retrieval, contagem de evidencias, identificadores dos documentos/versoes/chunks efetivamente recuperados, estado da chamada ao modelo, resultado e origem da falha do grounding, e uso de regeneracao.
- **E** um HANDOFF decidido antes do validador de grounding registra `groundingStatus=NOT_RUN`, mesmo que o runtime tenha emitido um marcador sintetico de handoff; esse caso nao e contado como rejeicao do validador.
- **E** `dispatchId` nao e inventado: o payload CRM recebido nao o contem, e a correlacao com o CRM usa `correlationId`.
- **E** uma falha tecnica em qualquer etapa registra `ERROR` sem transformar a falha em `NO_ACTION`.

#### AC-534 — Diagnostico estritamente sem conteudo sensivel

- **Dado** eventos internos contendo texto de paciente, prompt, conteudo de chunks, token e valores de erro arbitrarios
- **Quando** o resumo diagnostico e emitido
- **Entao** apenas campos e codigos permitidos chegam ao log; nenhum desses conteudos nem o segredo aparece no log ou na resposta ao CRM.
- **E** o logger padrao torna o evento terminal visivel em Production sem expor campos adicionais.
- **E** uma falha do logger nao altera a acao que o CRM receberia.

#### AC-535 — Perguntas comerciais e limites de atendimento

- **Dado** documentos publicados controlados para Botox, orcamento final, avaliacao, pagamento e regras de handoff
- **Quando** chegam as dez perguntas de preco, oferta, valor final, avaliacao, parcelamento, remarcacao, cancelamento, medicamento, procedimento nao especificado e agendamento
- **Entao** cada turno usa apenas evidencia elegivel do tenant, responde comercialmente quando ha suporte, encaminha pedidos de remarcacao/cancelamento e orientacao medicamentosa, pede esclarecimento para procedimento nao especificado e nao promete agendamento confirmado.
- **E** o diagnostico distingue resposta do modelo, regra deterministica, falha de grounding, fallback e erro tecnico sem alegar chamada ao modelo quando ela nao ocorreu.

### US-121 — Responder perguntas comerciais com dois assuntos

Como paciente, quero saber preco e caminho de agendamento no mesmo turno, para receber uma resposta util baseada nos documentos publicados sem uma transferencia desnecessaria.

#### AC-536 — Recuperacao equilibrada por assunto

- **Dado** uma pergunta sobre preco de Botox e agendamento e varios chunks de Botox que esgotariam o limite da busca
- **Quando** o retrieval consulta versoes publicadas do tenant
- **Entao** pelo menos um trecho elegivel de preco e um de agendamento entram nos quatro trechos apresentados ao modelo, quando ambos existem; a regra publicada de orcamento final tambem e considerada.
- **E** a classificacao conserva os dois assuntos `PRICE` e `SCHEDULING` sem perder a exigencia de evidencia factual.
- **E** nenhuma versao inativa, chunk inconsistente ou dado de outra organizacao pode ocupar essas vagas.

#### AC-537 — Grounding de afirmacoes independentes

- **Dado** uma resposta que une, por `e`, duas afirmacoes factuais independentes sobre preco e agendamento
- **Quando** cada afirmacao e sustentada por um chunk publicado diferente
- **Entao** o grounding aceita a resposta sem exigir que os dois fatos estejam no mesmo chunk.
- **E** preco divergente, regra de agendamento inventada ou qualificadores sem suporte continuam rejeitados.

#### AC-538 — Resposta parcial segura e acao terminal

- **Dado** evidencia publicada para apenas um dos assuntos pedidos
- **Quando** o modelo responde somente com o fato sustentado e uma pergunta comercial sem fato novo
- **Entao** o dispatch envia a resposta fundamentada; se o modelo afirmar detalhes do assunto sem evidencia, o dispatch permanece em HANDOFF com `UNSUPPORTED_FACTUAL_CLAIM`.
- **E** a pergunta real e as variacoes de preco, agendamento, parcelamento e orcamento final sao exercitadas por transporte de modelo controlado, sem respostas comerciais fixas no runtime.

#### AC-539 — Telemetria de evidencia sem confundir busca e validacao

- **Dado** um turno comercial com chunks recuperados cuja resposta foi rejeitada pelo grounding
- **Quando** o resumo terminal e emitido
- **Entao** `commercialEvidencePresent` indica a presenca de chunks candidatos no retrieval, `groundingPassed` registra separadamente o resultado da validacao e `promptChunkIds` identifica somente os trechos apresentados ao modelo.
- **E** o log continua contendo apenas UUIDs e codigos permitidos, sem texto de paciente, resposta, prompt ou segredo.

### US-122 — Diagnosticar a cobertura comercial sem atribuir causa nao comprovada

Como operador da Bruna, quero distinguir falta de candidatos para preco e agendamento de uma resposta sem suporte, para corrigir a fonte certa sem afrouxar o grounding.

#### AC-540 — Cobertura dos assuntos nos trechos apresentados

- **Dado** uma pergunta comercial com preco e agendamento
- **Quando** o retrieval seleciona os quatro trechos apresentados ao modelo
- **Entao** o evento terminal registra, por codigo permitido, quais assuntos solicitados possuem candidato lexical nesses trechos e quais estao ausentes.
- **E** distingue cobertura completa, parcial e ausente sem afirmar que um candidato prova a resposta ou registrar seu texto.

#### AC-541 — Origem da falha sem inferencia indevida

- **Dado** uma resposta rejeitada com candidatos para os assuntos pedidos
- **Quando** a pergunta do paciente exige evidencia
- **Entao** o diagnostico nao atribui automaticamente ao paciente a afirmacao sem suporte; registra origem indeterminada e preserva HANDOFF.
- **E** uma falha com assunto solicitado sem candidato e uma falha introduzida pelo modelo em turno sem demanda factual continuam distinguiveis por codigos estaveis.

#### AC-542 — Matriz comercial, operacional e clinica

- **Dado** a pergunta composta exata e as dez perguntas comerciais, operacionais e clinicas da homologacao
- **Quando** cada uma passa pelo dispatch CRM com transporte controlado
- **Entao** testes verificam intencao, IDs de evidencia elegivel, cobertura comercial, chamada ao modelo, grounding, acao, origem e motivo terminal.
- **E** os guardas de remarcacao, medicamento e pedido humano permanecem deterministas, sem WhatsApp ou OpenAI real.

#### AC-543 — Evidencia parcial, ausente e contraditoria

- **Dado** fontes publicadas de um assunto, fontes ausentes, contraditorias, rascunho ou de outro tenant
- **Quando** ocorre retrieval e grounding
- **Entao** somente suporte publicado e coerente pode autorizar uma afirmacao; resposta parcial sem fato novo pode ser enviada, mas valor, gratuidade, horario e regra inventados falham fechados.
- **E** o diagnostico informa apenas metadados seguros de cobertura e resultado.

## Fora de escopo

- Inserir documentos reais, criar credenciais, usar OpenAI real, escrever no Supabase de Production ou fazer deploy.
- Criar nova tabela de chunks ou endpoint publico de ingestao.

## Suposicoes

| ID | Suposicao | Status | Resolucao |
|---|---|---|---|
| ASM-047 | Uma versao publicada de maior `version_number` e a versao atual quando duas publicadas coexistem para o mesmo documento. | confirmada | Coerente com o contrato de substituicao; os documentos Hartmann publicados foram consultados em modo somente leitura e o teste cobre a concorrencia. |

## Perguntas em aberto

| ID | Pergunta | Status | Resposta |
|---|---|---|---|
| Q-009 | A primeira base pode ser publicada sem aprovacao humana registrada? | respondida | Nao. O contrato de ingestao exige aprovador identificado antes de qualquer publicacao; a pessoa sera designada na operacao futura. |
| Q-010 | Qual etapa determinou o HANDOFF do dispatch `7b561ffc-f038-4219-bee7-c16b94da2a09`? | respondida | Indeterminavel retrospectivamente: o dispatch nao persistiu eventos de modelo ou grounding. Logs de retrieval provam busca por Botox, mas nao a causa terminal. Exige telemetria segura por etapa em uma proxima homologacao controlada; nao executar atendimento real para reconstruir o incidente. |
| Q-011 | Qual afirmacao especifica falhou no grounding do dispatch `6b307701-623f-43c1-a358-5d07cdb2f6d3`? | respondida | Indeterminavel retrospectivamente: os seis chunkIds foram vinculados por leitura limitada a tres versoes publicadas, mas o evento nao registra a ordem dos quatro chunks apresentados ao modelo nem o texto rejeitado. A falha do grounding e comprovada; atribuir uma afirmacao exata seria inferencia sem prova. A nova telemetria registra `promptChunkIds` para proximos dispatches sem guardar conteudo. |
