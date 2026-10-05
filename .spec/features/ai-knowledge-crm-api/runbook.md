# Operação da API privada (sem deploy nesta entrega)

## Preparar ambiente de teste isolado

Instalar `requirements-admin.txt` no ambiente Python. Configurar via secret
manager do host: `CRM_KNOWLEDGE_SERVICE_TOKEN` aleatório com ≥32 caracteres,
diferente de `CRM_DISPATCH_SERVICE_TOKEN`; `KNOWLEDGE_DATABASE_URL` para o banco
**da IA**; `OPENAI_API_KEY` (ingest); `SUPABASE_URL` e
`SUPABASE_SERVICE_ROLE_KEY` (smoke). Não imprimir nem colar valores em logs.
Não alterar as credenciais do projeto Production durante esta tarefa.

O servidor já usado pelo dispatch em `python -m ai_agent_runtime.crm_dispatch`
recebe as novas rotas na mesma porta 8083. Bind padrão `127.0.0.1`; o ambiente
futuro precisa publicar somente através de rota interna com TLS e controle de
rede. O CRM Backend acessa essa rota; frontend nunca recebe token.

O operador CRM deve verificar sessão, membership e papel antes de cada chamada.
Usar `correlationId` UUID novo para rastrear cada operação, preservar o
`logicalName` estável e guardar no CRM o `documentId`/`versionId` retornado.
A URL/body e os erros exatos estão em `api-contract.md`.

## Fluxo na futura interface CRM

1. Escolher organização após checar permissão; enviar `organizationId` explícito.
2. Ler arquivo `.md` UTF-8 no backend CRM ou receber seu texto de upload e
   repassar JSON `logicalName`, `filename`, `content` para `dry-run`.
3. Conferir `changed`, hash, contagem e versão proposta. Chamar `ingest` apenas
   após decisão operacional. Resultado é `REVIEW_REQUIRED`.
4. Usar `GET /documents/{id}/versions/{versionId}/review` para mostrar os chunks
   ao revisor. Registrar ato humano com `validate`, enviando seu UUID como actor.
5. Conferir estado `APPROVED`; chamar `publish` com ator autorizado. Confirmar
   GET versions/list e `smoke` com termos revisados. Se timeout de resposta,
   consultar estado antes de repetir; retry é seguro.
6. Para retirar uma publicação incorreta, `deactivate` por versionId/actor.
   Restaurar conteúdo antigo como nova versão, nunca editando SUPERSEDED à mão.

## Verificações de desenvolvimento

```bash
export ADMIN_TEST_PYTHON="$PWD/.venv/bin/python"
node --test test/ai-knowledge-crm-api/api.test.js
node --test --test-reporter=tap
node .agents/skills/onp-spec-driven/scripts/onp-spec.mjs verify ai-knowledge-crm-api
node .agents/skills/onp-spec-driven/scripts/onp-spec.mjs audit --ci
git diff --check
```

A suíte API usa PostgreSQL/pgvector descartável e listener HTTP loopback. Não
usa Production, nem publica Hartmann. O CLI antigo continua disponível como
fallback, inclusive para documentos CLI sem manifesto persistido em auditoria.
