# Design — API privada de conhecimento

## Base inspecionada

Lidos integralmente: `ai-knowledge-admin`, `knowledge.py`, CLI, parser,
`crm_dispatch.py`, autenticação do transport CRM→IA, configuração da organização,
logging/correlationId. Não há AGENTS.md na raiz da IA; o AGENTS.md do repositório
CRM vizinho foi lido para entender sua convenção, sem alterar o CRM.

## Decisões

- A aplicação HTTP existente em `crm_dispatch.py` recebe também rotas
  `/internal/knowledge/*` no mesmo listener. Reusa função Bearer/hmac do dispatch.
  Token separado `CRM_KNOWLEDGE_SERVICE_TOKEN` (mínimo 32 caracteres) limita
  privilégio: o token de dispatch não aprova/publica. Nunca aceitar tenant por
  header; cada requisição envia `organizationId` no JSON ou query autenticada.
- Backend CRM é responsável por autenticar usuário, membership e papel de admin.
  Token privado identifica serviço, não usuário; `actor` é o identificador auditável
  que o CRM atesta. IA confere status ativo da organização no SQL real para cada
  operação, inclusive leitura; sem fallback env e sem confiar em conteúdo.
- JSON UTF-8, um documento por request. `logicalName` estável determina identidade
  `logicalName.md` (regra UUID determinística existente); `filename` só metadata.
  Conteúdo Markdown codificado como string JSON, sem filesystem compartilhado.
  Os limites de fonte/chunk existentes (512.000 bytes/6.000 chars) são mantidos;
  1 documento/request permite rollback e UI simples; body máximo 1.100.000 bytes
  acomoda JSON UTF-8 e escaping, com 400/413 em excesso.
- `KnowledgeAdmin` continua único writer. A ingestão persiste manifesto sem texto/
  vetor em `operational_audit_events` **na mesma transação**, com correlationId.
  Validação/publicação por versionId recuperam o manifesto e usam os mesmos
  métodos `validate`/`publish` do CLI. Legados ingeridos antes desse registro
  precisam ser validados via CLI (fonte+manifesto) ou reingestidos identicamente
  pela API para criar o registro, sem nova versão.
- List/detail/review usam o mesmo repositório com SQL sempre escopado a tenant.
  Ausência/cross-tenant têm 404 idêntico. Lista/detalhe não incluem conteúdo;
  `/review` devolve chunks do documento solicitado para revisão humana.
  Vetores jamais retornam.
- Locks por linha de organização existentes serializam ingest/validate/publish.
  Requisição idêntica já é idempotente por hash/versão e estado. Não se introduz
  `Idempotency-Key` externo: o contrato define retry seguro e stale version 409.
- Logger allowlist registra operação/correlation/tenant/IDs/actor/outcome, jamais
  body, erro bruto ou Authorization. Writes críticos auditados na transação.
  Dry-run/smoke e falhas geram evento estruturado sem conteúdo no logger, mantendo
  dry-run SQL READ ONLY. Sem nova migration.
- Timeout PostgreSQL por statement 60s existente; OpenAI 30s por embedding;
  limite total de operação 120s checado entre passos, que causa rollback.
  O gateway do CRM deve usar timeout maior que 150s. Sem prometer cancelamento
  imediato durante chamada remota já em curso.
- Servidor HTTP suprime access log padrão; erros de fornecedor são códigos
  constantes. Erros de recurso estrangeiro retornam 404 sem revelar existência.
