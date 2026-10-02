# Cutover CRM multi-tenant — desenho local

O endpoint CRM e o adapter Z-API legado sao entradas distintas. O primeiro
recebe `organizationId` apos service token; nao consulta telefone, instancia
ou mapas Z-API. `ORGANIZATION_CONFIG_SOURCE` escolhe explicitamente
`supabase` (default/fail closed), `env` (desenvolvimento/rollback) ou `hybrid`
(Supabase primeiro; env apenas para organizacao ausente). Erro de transporte,
status inativo ou config ausente/incompleta rejeitam mesmo em hybrid.

No caminho Supabase, a configuracao vem de `organizations` e
`organization_ai_configs`, ambas filtradas por UUID e ativas. A config
carrega sua origem para selecionar o provedor de credencial: Supabase Vault
para origem Supabase; `ORGANIZATION_CREDENTIALS_JSON` somente para origem env.
A ref publica tem formato `vault:<uuid>` e nao contem o secret. Uma RPC
restrita a `service_role` junta a linha ativa de `organization_credentials`
com `vault.decrypted_secrets` por organizacao, provider, ref e nome Vault
`openai:<organization_id>`. Essa vinculacao impede que uma ref de A copiada
para a linha de B entregue o secret de A. O runtime exige
resultado unico e falha fechado para zero/multiplas linhas ou erro de rede.
O segredo existe somente em memoria durante a chamada OpenAI.

O modelo/reasoning continuam globais (`OPENAI_RESPONSES_MODEL` e
`OPENAI_REASONING_EFFORT`) porque o schema atual nao tem colunas por
organizacao para eles; as regras comerciais e a identidade ja sao locais.
RAG consulta o Supabase da IA com `organization_id` do evento em todas as
queries. A memoria de conversa pertence ao `AgentState` criado por request.

O fluxo Z-API legado preserva seus envs e fallback atuais para rollback. O
cutover nao roda migration, nao cria secret real e nao altera Production.
Antes de ativar o modo Supabase em um ambiente: aplicar/revisar a migration,
confirmar Vault disponivel, criar uma linha de config e uma credencial Vault
por organizacao, testar a RPC com `service_role` e negar `anon`/`authenticated`.
