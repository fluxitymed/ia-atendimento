# Relatorio de confiabilidade WhatsApp/Z-API

Revisao local de 28/09/2026, na feature existente. Sem deploy, mensagens reais, alteracao de credenciais, playbook, KB Carvalho ou semantica de RAG/grounding/handoff.

## Causas comprovadas por reproducao

- **Concorrencia no inbound:** o adapter direto verificava `has_processed` antes da rede e so gravava o resultado depois do outbound. Dois callbacks simultaneos atravessavam a verificacao e produziam duas geracoes/envios. O batching tambem separava consulta/reserva e ignorava o retorno da reserva. Testes agora exigem uma chamada/um envio.
- **Timer obsoleto:** callbacks identificavam apenas conversationId. Cancelamento nao impede callback ja disparado; ele podia remover o proximo lote. Reproducao falhou antes da mudanca e passa com identidade/geracao por lote.
- **Persistencia permissiva e concorrente:** JSON invalido era interpretado como historico vazio; snapshots de processos distintos nao se coordenavam e usavam o mesmo arquivo temporario. Reproducao de corrupcao confirmou a falha. Agora erro de leitura/corrupcao interrompe o processamento, transacoes recarregam sob flock e escrita usa fsync + replace.
- **Estado compartilhado no graph:** `_active_state` era atributo unico do graph compartilhado. Conversas concorrentes podiam misturar eventos de runtime. Agora usa ContextVar; teste de conversas paralelas valida que eventos ficam em seu proprio estado.
- **Caminhos sincronos HTTP:** audio/STT, early flush e batching desabilitado podiam manter a requisicao aberta durante chamadas remotas. O servidor agora admite em fila limitada antes de confirmar e executa fora da thread HTTP.

## Incidentes A, B e C

| Caso | O que o codigo permite concluir |
|---|---|
| A: aproximadamente 13 minutos | Nao e debounce normal. Retrieval faz ate 8 consultas de termos + consulta de versoes + ate 3 consultas de catalogo, cada chamada com timeout de socket de 20s. A operacao inteira pode ser repetida 3 vezes. Esse caminho pode se aproximar de 12 minutos, antes de modelo, uso/CRM e outbound. E uma explicacao possivel, nao a causa comprovada do incidente. |
| B: aproximadamente 58 minutos | Nao ha timer de batching de 58 minutos. Espera atras de turnos demorados, callbacks entregues tarde, I/O e timeout de socket sem deadline global permitem atrasos acumulados. Nao ha logs para escolher entre essas causas nem provar a duracao observada. |
| C: respostas semelhantes 10:29 e 10:44 | Duplicidade por corrida foi reproduzida. Isso nao prova que ocorreu nesse incidente. IDs diferentes, dois destinos ou outro processo continuam hipoteses que exigem correlacao dos logs de producao. Sem nova evidencia, nao deduplicar por semelhanca textual. |

Timeouts atuais foram preservados: Supabase retrieval 20s por request; OpenAI Responses 30s; outbound Z-API 30s; STT 60s por tentativa; repositorio CRM 15s; configuracao/usage Supabase 30s. Esses sao timeouts de transporte, nao SLA fim a fim. Retries de retrieval/STT e regeneracao permitida pelo grounding continuam sem alterar semantica. O transporte de outbound nao possui retry automatico.

## Auditoria das 13 fontes solicitadas

| Fonte | Resultado/protecao |
|---|---|
| Mesmo providerMessageId | Reserva atomica account/message, claim de turno e constituents persistidos; concorrencia/reload cobertos. |
| Mesmo conteudo, ID diferente | Nao ha prova de que representa a mesma mensagem; mantido como novo inbound para nao perder respostas legitimas. |
| Dois timers | Um timer efetivo, com deadline minimo entre debounce e max wait; callbacks cancelados so podem atuar no proprio lote/geracao. |
| DEBOUNCE x MAX_WAIT | Pop atomico; teste concorrente exige um flush. |
| Threads | RLock curto no store e lock de conversa cobrindo todos os caminhos do adapter; nenhum lock global durante rede. |
| Envio sem confirmacao | Intencao ATTEMPTING antes de chamar provider, SENT apenas com ID, UNKNOWN em falha; nenhum reenvio automatico. |
| Callback enviado como inbound | Filtro de tipos existentes e fromSelf preservados; testes de status/fromMe exigem zero runtime/outbound. |
| Restore apos restart | Claims STARTED/reservados e outbound ATTEMPTING nao expiram nem sao retomados automaticamente. |
| Dois processos/instancias | flock transacional e lock de conversa no mesmo disco; servidor recusa segunda instancia com mesmo store. Hosts com discos distintos nao sao coordenados. |
| Dois destinos de webhook | Configuracao live nao foi consultada/alterada. Usar um destino ativo; dois destinos com stores independentes nao sao seguros. |
| fromMe | Ignorado antes de runtime, inclusive no batching. |
| phone/LID | Resolver existente preservado, alias transacionado; regressao cobre mapeamento persistente e isolamento de tenant. |
| Reprocessamento apos deploy | Nenhuma fila e restaurada para gerar resposta antiga; claims duraveis sobrevivem ao restart. |

A documentacao oficial confirma que [o callback recebido pode incluir mensagens proprias](https://developer.z-api.io/en/webhooks/on-message-received). O contrato consultado de [send-text](https://developer.z-api.io/message/send-text) nao oferece uma chave cliente de idempotencia em que esta implementacao possa se apoiar. Portanto timeout ambiguo nao autoriza novo POST.

## Estrategia implementada

Chave do turno: SHA-256 da organizacao, provider account e lista ordenada de chaves fisicas do lote. runtimeInvocationId e UUID deterministico desse turno. Claim ocorre antes do runtime; constituents ficam reservados, e o resultado registra tambem cada ID fisico. Nao existe TTL de claim que permita um worker atrasado enviar novamente.

Intencao de outbound e persistida antes da rede. Mesmo se o processo cair depois da entrega e antes de salvar o historico, a intencao bloqueia repeticao. UNKNOWN/ATTEMPTING exigem reconciliacao humana com o provedor; nao ha reenvio cego. A garantia e **no maximo uma tentativa automatica**, nao entrega exatamente uma vez: pode haver perda de resposta em crash/falha.

O lote e destacado sob lock e possui geracao. Mensagem durante flush fica no proximo lote; ao liberar o turno, a continuacao segue o comportamento existente de flush imediato. Early flush e midia tambem passam pela serializacao do store. O servidor possui um unico dono do batching por arquivo de store.

HTTP: 8 workers e capacidade total de 128 trabalhos em processamento/fila; duplicatas nao ocupam nova vaga. Saturacao retorna 503 + Retry-After sem consumir claim. O aceite 200 ocorre depois da reserva duravel, sem esperar OpenAI, STT ou Z-API. Nao e uma fila de entrega recuperavel: trabalho aceito interrompido por restart nao sera refeito automaticamente.

## Latencias e operacao no Render

Eventos de timestamp correlacionados por organizationId, conversationId, runtimeInvocationId e providerMessageId:

- webhook_ingress_received_at
- batch_started_at / batch_flushed_at
- lock_acquired_at / runtime_started_at
- retrieval_started_at / retrieval_completed_at
- model_call_started_at / model_call_completed_at
- outbound_started_at / outbound_completed_at

`turn_latency_summary` possui apenas os quatro identificadores, outcome, outboundSent e ingress_to_batch_ms, batch_wait_ms, lock_wait_ms, retrieval_ms, model_ms, outbound_ms, total_processing_ms, ingress_to_outbound_ms. Nenhum conteudo, telefone, nome ou credencial e acrescentado a esses eventos. Tempos monotonicamente medidos; timestamps UTC. Tempo de modelo soma tentativas de regeneracao. Estagio pulado tem duracao zero; sem outbound, ingress_to_outbound_ms fica null. Outbound concluido significa confirmacao HTTP com ID, nao entrega ao dispositivo do paciente.

Watchdogs emitem `slow_retrieval` (10s), `slow_model_call` (20s), `slow_outbound` (10s), `slow_turn` (45s), inclusive enquanto uma chamada permanece bloqueada. Apenas avisam; nao cancelam chamadas saudaveis. O slow_turn cobre processamento/lock a partir do inicio do adapter; tempo anterior de fila/batch fica nas metricas finais. Audio tem watchdog durante materializacao e resumo proprio quando termina em retry/handoff.

Observar apos deploy:

1. `webhook_accepted`: aceite rapido; comparar ingress com batch para identificar fila/I/O/STT.
2. `message_batch_age_ms`: cerca de 6000ms normal, maximo configurado 12000ms enquanto a conversa esta livre. Ocupacao do turno anterior pode adiar proximo flush e nao deve ser confundida com debounce.
3. `slow_*` e `turn_latency_summary`: separar lock, retrieval, modelo e outbound; agrupar por runtimeInvocationId.
4. `duplicate_detected` / `provider_message_duplicate_rejected` / `outbound_duplicate_suppressed`: supressoes esperadas de retries, nao novos envios.
5. `outbound_outcome_unknown`, `ingress_processing_failed`, `batch_processing_failed`: investigar e reconciliar sem apagar claims.
6. `webhook_capacity_exceeded`: pressao de fila; investigar chamadas lentas antes de aumentar custo.
7. `WHATSAPP_STORE_UNREADABLE`, `WHATSAPP_STORE_DISAPPEARED`, `ZAPI_SERVICE_ALREADY_RUNNING_FOR_STORE`: corrigir disco/deploy; nunca limpar store para retomar.

Manter disco persistente em /var/data e um processo servidor/um destino ativo. WEB_CONCURRENCY nao configura o ThreadingHTTPServer deste comando. Health check /health nao espera runtime e nao comprova saude de OpenAI/Supabase/Z-API. Nenhuma infraestrutura foi aumentada.

## Testes e limites residuais

19 novos casos executaveis, cobrindo os 16 cenarios pedidos: mensagem unica, repeticao e concorrencia, timer obsoleto/flush duplo, agrupamento, inbound durante flush, callbacks, retry/restart, falhas antes/depois do envio, conversas independentes/serializadas, latencias com relogio e watchdog controlados, aliases e isolamento. Adicionais: dois processos, singleton de servidor, fsync falhando e arquivo desaparecido.

Suite completa: 266 testes, 266 PASS, 0 FAIL, 0 skip/todo. Compileall e git diff --check passaram. Provas ONP sao atualizadas para todas as features porque compartilham o runtime. Resultado final do audit deve acompanhar este relatorio na resposta de entrega.

Riscos: disco local precisa ser realmente persistente; JSON cresce com historico e transacoes curtas ainda podem sofrer com I/O; filas/timers sao locais; locks e disco independentes nao coordenam hosts; entrega externa pode acontecer depois do timeout; ID diferente nao e prova de duplicata; nao existe deadline absoluto novo, por orientacao de nao interromper chamadas saudaveis. Logs reais de Render/Z-API ainda sao necessarios para atribuir A/B/C.

## Arquivos alterados

- `src/ai_agent_runtime/whatsapp/channel.py`: transacoes e locks duraveis, claims de turno/outbound, fail-closed e fsync.
- `src/ai_agent_runtime/whatsapp/adapter.py`: claim antes de runtime, lock por conversa, intencao de envio e resumo de latencia.
- `src/ai_agent_runtime/whatsapp/batching.py`: reserva atomica, timer com geracao, flush protegido e observabilidade de midia.
- `src/ai_agent_runtime/whatsapp/ingress.py`: novo componente interno de aceite HTTP limitado e assincrono.
- `src/ai_agent_runtime/whatsapp/latency.py`: novo componente interno de timestamps, metricas e watchdogs.
- `src/ai_agent_runtime/whatsapp/zapi_webhook.py`: timestamp de ingresso e 503 em saturacao.
- `src/ai_agent_runtime/whatsapp/zapi_server.py`: integra ingress assincrono, singleton de servidor e inicializacao segura do store.
- `src/ai_agent_runtime/graph.py`: estado ativo por contexto e observacao dos estagios.
- `test/ai-whatsapp-zapi-provider/reliability_cases.py` e `zapi-reliability.test.js`: 19 novos testes offline com rastreabilidade literal ONP.
- `.spec/features/ai-whatsapp-zapi-provider/spec.md`, `tasks.md`, `reliability-design.md`, `reliability-report.md`, `render-web-service.md`: criterios, tarefas, projeto e operacao da feature existente.
- `.spec/verification/*.json`: provas regeneradas pelo ONP e sinais de auditoria; alguns desses arquivos ja estavam modificados ao iniciar a tarefa.

O plano mecanico foi gerado para inspecao e a implementacao foi manual nesta sessao. Os scripts headless gerados foram removidos ao concluir, para nao deixar um executor pendente com modelos sugeridos que nao foram utilizados.
