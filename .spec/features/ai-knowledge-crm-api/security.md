# Notas de segurança — Knowledge Admin API

- Fronteira privada: mesmo Bearer/hmac de `crm_dispatch.py`, com token knowledge
  próprio (`CRM_KNOWLEDGE_SERVICE_TOKEN`, mínimo 32 caracteres), distinto do
  dispatch. Ausência/mismatch retorna 401 antes de consultar banco. O listener
  permanece loopback por padrão; reverse proxy privado com TLS é requisito de
  operação. O token nunca vai a browser, storage de frontend ou query string.
- Autorização de pessoa: CRM Backend valida sessão, membership e papel antes de
  usar o token. IA valida UUID do ator e organização ativa no PostgreSQL. O token
  não representa uma pessoa. `organizationId` do JSON/query autenticado é único
  escopo; header não autenticado e frontmatter são ignorados/rejeitados.
- SQL escopado por organization_id em cada leitura e escrita. Lookup de recurso
  estrangeiro/inexistente devolve 404 indistinguível. `KnowledgeAdmin._inspect`
  verifica coerência documento/versão/chunk/índice antes de aprovação/publicação.
- Manifestações de integridade sem conteúdo/embedding ficam em
  `operational_audit_events` na mesma transação da ingestão. Isso permite
  validate/publish por versionId sem confiar em hashes enviados de volta pelo
  cliente. O evento preserva IDs, SHA-256, digest de chunks/índice, ator,
  correlationId e filename original; nenhuma chave ou vetor.
- Dry-run usa transação READ ONLY. Ingest, approve e publish usam lock na linha
  da organização. Publicação e supersession fazem um commit; falha reverte tudo.
  Idempotência cobre retries sem cabeçalho externo adicional.
- Logs são allowlist: operação, tenant, IDs, ator UUID, correlationId, outcome.
  Não registram request body, Markdown, consultas de smoke, headers, segredos,
  DSN, stack traces ou embeddings. A única resposta com texto é `/review`,
  necessária à aprovação e acessível apenas ao backend autenticado.
- Limites no contrato HTTP: 1 documento, 512.000 bytes de conteúdo, 1.100.000
  bytes de JSON, chunk de 6.000 caracteres; SQL statement 60s, OpenAI 30s por
  embedding, orçamento total 120s entre etapas. Exceder falha fechado.
- Nenhuma migration nem policy RLS nova. A conta PostgreSQL administrativa é
  backend-only. `service_role` Supabase é usada apenas pelo runtime de smoke;
  não deve ser colocada no CRM/frontend.
- Limitação estrutural: token de serviço dá alcance a todos os tenants ativos
  para os quais CRM está autorizado operacionalmente. A IA não possui tabela de
  membership do CRM. A próxima implementação no CRM deve impor membership e
  papel administrativo antes de invocar este contrato, com teste cross-org.
