# Confiabilidade do pipeline existente

Execucao sequencial na sessao atual autorizada pelo pedido de autonomia, sem agentes extras ou mudanca de modelo.

1. Reproduzir concorrencia, callback de timer obsoleto e reload corrompido.
2. Manter JSON compativel: transacoes curtas com RLock + flock, reload sob lock e fsync/replace. Lock de conversa separado, nunca manter lock global durante rede. Claim duravel do turno e intencao outbound antes de enviar; nenhuma retomada automatica de claims apos crash.
3. Timers com identidade/geracao; lote destacado atomicamente. Novo inbound permanece no proximo lote. Serializacao no adapter cobre early flush e midia.
4. Ingress HTTP limitado em background; reserva duravel antes do aceite. O trabalho aceito nao e restaurado automaticamente apos restart (preferencia por no-maximo-uma-vez). Sob saturacao devolver 503 sem reservar.
5. Contexto de latencia por thread/turno e watchdogs apenas de aviso; nenhuma nova interrupcao de chamadas saudaveis. Corrigir estado ativo compartilhado do graph para contexto local.
6. Testes offline, regressao completa, ONP verify e audit. Nenhuma chamada a pacientes, deploy ou alteracao de credenciais.

Sem evidencia suficiente para deduplicar por conteudo: repeticoes legitimas com novos IDs continuam turnos diferentes. Dois hosts com discos independentes nao compartilham exclusao; manter um destino/servico ate introduzir coordenacao compartilhada. JSON cresce com historico: instrumentar e documentar custo de I/O, sem aumentar infraestrutura.
