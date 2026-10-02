# ONP — runtime IA multi-tenant local (2026-09-29)

Sem deploy, acesso a Production, cadastro real ou credenciais reais.

- Regressao completa: 275 testes PASS, 0 falhas, 0 skips.
- `onp-spec verify ai-organization-runtime-config`: 24/24 criterios da
  feature com prova PASS; a prova esta em
  `.spec/verification/ai-organization-runtime-config.json`.
- A RPC Vault foi executada em PostgreSQL temporario com dados ficticios:
  service_role resolveu a credencial da propria organizacao sem exibir o valor; uma linha de B
  apontando para a ref de A recebeu zero linhas, e anon/authenticated tiveram
  EXECUTE negado. Esse teste usa uma view
  Vault simulada e nao substitui homologacao no Supabase real.
- `audit --ci` final: exit 0, 11 features, 493/493 criterios com teste e
  prova, 0 erros e 0 avisos. As provas das outras dez features foram
  renovadas apos a mudanca de codigo compartilhado.

Este documento registra evidencia local; a aprovacao operacional depende de
aplicar/revisar a migration e testar Vault, grants, RAG e CRM → IA em staging.
