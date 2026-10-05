# Verificação — API privada de conhecimento

Data: 2026-10-05. PostgreSQL 18 com pgvector local descartável, Python 3.14,
psycopg 3.2.10; listener HTTP em loopback. Fontes sintéticas, sem Hartmann.

## Provas executadas

- Suíte focada: 18/18 testes PASS, um por critério de aceite, sem skip/todo.
- Regressão completa: 310/310 testes PASS, sem falhas/skip/todo.
- Autenticação ausente/incorreta e token de dispatch recusados antes do banco.
- Requisições GET/POST reais no listener compartilhado; JSON, status e headers
  verificados. Organização B não lê nem publica versão de A.
- PostgreSQL real provou retry sem versões/embeddings duplicados e publicação
  concorrente sob lock. Novo draft torna publicação da versão anterior obsoleta.
- CLI antiga e API produzem o mesmo ID de documento/versão quando logicalName
  corresponde ao filename; API pode registrar manifesto para versão CLI idêntica.
- Falha simulada de fornecedor com segredos não aparece em resposta/log e reverte
  escrita. Dry-run mantém quatro tabelas e auditoria vazias.
- O caminho de revisão retorna somente chunks solicitados; listagem/detalhe não
  retornam Markdown ou vetores. Smoke retorna somente IDs/contagens.

## Limites da prova

Não houve conexão com Production, deploy, carga Hartmann, chamada OpenAI real ou
integração da UI/Backend CRM. A autorização de usuários/membership deverá ser
implementada e testada no CRM; a IA autentica o serviço e verifica tenant no banco.
A URL privada/TLS e provisioning de token são operação futura. A compatibilidade
com textos reais dependerá de dry-run/revisão humana. A API usa o transporte lexical
existente no smoke, sem provar qualidade clínica das respostas.

## Gate final

- ONP verify `ai-knowledge-crm-api`: 18/18 critérios PASS, 310 testes lidos, exit 0.
- As provas das demais 13 features foram renovadas; cada arquivo de prova registra
  310 testes lidos e exit 0. Houve um exit 1 intermitente numa execução da prova
  `ai-organization-runtime-config` com seus 24 critérios PASS; a regressão bruta
  repetida passou 310/310 e a prova dessa feature foi repetida com exit 0.
- `git diff --check`: exit 0.

```text
resumo: 14 feature(s) · 118 história(s) de usuário · 530 critério(s) de aceite · 530/530 com teste · 530/530 provados · 5 pergunta(s) aberta(s)
✔ auditoria limpa (0 aviso(s))
```

As cinco perguntas em aberto são de features anteriores e não foram classificadas
como aviso/bloqueio pelo gate desta entrega. Classificação:
`READY_FOR_CRM_KNOWLEDGE_INTEGRATION`.

