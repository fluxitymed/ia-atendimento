# Verificacao — RAG Hartmann e diagnostico do dispatch CRM

## Provas locais em 2026-10-07 e 2026-10-08 (America/Bahia)

- `ADMIN_TEST_PYTHON=.venv/bin/python node --test --test-concurrency=1 test/**/*.test.js`: 321/321 passaram. Inclui os dez cenarios Hartmann, diagnosticos terminais, isolamento multi-tenant e testes PostgreSQL temporarios. O transporte OpenAI e o retrieval dos cenarios comerciais sao controlados; nenhum atendimento ou mensagem real foi executado.
- Regressao sem PostgreSQL: 288/288 passaram. Regressao PostgreSQL isolada: 33/33 passaram com banco temporario local.
- `ADMIN_TEST_PYTHON=.venv/bin/python node .agents/skills/onp-spec-driven/scripts/onp-spec.mjs verify ai-hartmann-knowledge-readiness`: 9/9 criterios com prova PASS, 321 testes lidos, runner exit 0.
- `onp-spec verify` renovou as provas de 13 features afetadas pelo codigo compartilhado, cada uma com os 321 testes lidos e criterios da feature em PASS. Uma execucao de `ai-crm-conversation-runtime` registrou runner exit 1 sem falha em seus criterios; a repeticao fechou 20/20 e runner exit 0.
- O comando de teste em `onpspec.config.json` usa `--test-concurrency=1`: cada caso PostgreSQL inicia uma instancia temporaria; a execucao paralela esgotava o limite local de memoria compartilhada. Segmentos criados por processos de teste ja encerrados foram removidos apos confirmacao de `NATTCH=0` e PID criador inexistente; o segmento ativo do Postgres do sistema foi preservado.
- Apos o ajuste de semantica do grounding, os 11 testes focados passaram, a regressao completa passou 321/321 e as provas ONP das 14 features foram renovadas com runner exit 0. Durante as repeticoes, `ai-runtime-integrations` registrou tres execucoes intermitentes com 18/18 criterios PASS mas runner exit 1; uma regressao TAP direta passou 321/321, e a prova final dessa feature passou 18/18 com runner exit 0. Nenhum erro foi mascarado na prova final.
- `onp-spec audit --ci`: 14 features, 535/535 criterios com teste e prova, 0 erros, 0 avisos. As 14 provas JSON registram runner `exitCode=0`.
- `git diff --check`: passou.

## Limite da prova

Os logs existentes do incidente `142f8614-97c4-4f85-a202-df0cb51b39d0` provam a busca por Botox, mas nao registram a resposta do modelo ou o veredito terminal do grounding. A causa precisa daquele HANDOFF antigo permanece indeterminavel. A nova telemetria so se aplica a execucoes posteriores a um deploy autorizado; ela nao reconstroi eventos passados.

## Para fechar o gate

Depois de deploy autorizado, uma homologacao controlada em staging deve correlacionar `crm_dispatch_decision` ao resultado do CRM para `SEND_MESSAGE`, `HANDOFF` e `NO_ACTION`, sem incluir texto de paciente, prompt, chunk ou segredo no log. A causa terminal do HANDOFF historico continua indeterminada porque nao existia telemetria suficiente naquele dispatch.
