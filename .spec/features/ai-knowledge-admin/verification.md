# Verificação — ingestor administrativo

Data: 2026-10-05. Ambiente: PostgreSQL 18 / pgvector 0.8.1 local descartável,
Python 3.14, psycopg 3.2.10. Sete fontes sintéticas UTF-8; nenhuma fonte Hartmann.

## Resultados executados

- Suíte focada: 13/13 PASS; sem skip/todo.
- Regressão completa: 292/292 PASS; sem falhas, skip ou todo.
- ONP verify ai-knowledge-admin: 13/13 critérios provados, 292 testes lidos, exit 0.
- O audit CI inicial exigiu renovar as provas das outras 12 features por mudança
  global de código/testes. As 12 provas foram regeneradas com o runner, todas com exit 0, sem edição manual.
- git diff --check: sem erros.

## Evidências relevantes

Banco real, migrations canônicas e pgvector; nenhum substituto em memória.
Ingestão repetida e duas conexões concorrentes mantêm uma única versão por fonte
sem embeddings extras. Alteração de uma fonte cria apenas uma versão e conserva
publicação antiga até commit. Injeção de erro de embedding reverte todo o lote;
trigger PostgreSQL falhando na segunda publicação reverte também a primeira
publicação e a primeira supersession. Fontes, chunks e vetores adulterados são
recusados. A validação de um lote falhando no segundo item reverte o primeiro.

O runtime existente é exercitado com transporte SQL local: DRAFT/REVIEW_REQUIRED/
APPROVED não servem; PUBLISHED serve; SUPERSEDED/INACTIVE/expirado não servem;
organização B não recebe A. A regressão existente cobre demais estados e grounding.
Foi identificado e corrigido o descarte da grafia UTF-8 nas consultas lexicais.

A CLI é exercitada para argumentos ausentes, dry-run real e falha de fornecedor
com segredos sentinela. Mensagens externas/SQL/DSNs não são propagadas. O teste de
READ ONLY tenta UPDATE e observa rejeição pelo PostgreSQL.

## Limites da prova

Não houve conexão ou escrita remota, deploy, chamada real de embeddings ou uso de
credenciais Vault. O transporte HTTP real PostgREST/OpenAI não foi exercitado com
fontes reais. Essa confirmação pertence à operação controlada futura A–E do runbook.
O smoke não substitui a revisão clínica; parser conservador pode exigir estruturação
editorial dos sete arquivos ainda não fornecidos. Locks coordenam esta ferramenta;
operadores não devem usar escritores SQL externos concorrentes para o mesmo tenant.

## Classificação

READY_FOR_CONTROLLED_KNOWLEDGE_INGESTION. Gate CI concluído com exit 0.
Pré-requisitos operacionais descritos no runbook; nenhuma base real aprovada/publicada.

## Saída final do ONP audit --ci

```text
resumo: 13 feature(s) · 117 história(s) de usuário · 512 critério(s) de aceite · 512/512 com teste · 512/512 provados · 5 pergunta(s) aberta(s)
✔ auditoria limpa (0 aviso(s))
```

As cinco perguntas contabilizadas pertencem a especificações anteriores, não a esta
feature. O motor não as classificou como bloqueio ou aviso neste gate.

A fase Aprender consultou `licoes sugerir`; nenhuma lição nova foi adicionada.
Os achados resolvidos foram ausência inicial de testes/arquivo durante construção
e expiração global de provas; os requisitos e o rigor do gate foram preservados.

