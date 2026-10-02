# Runtime IA multi-tenant: operacao local e inventario

Escopo: endpoint autenticado CRM → IA. O adapter Z-API antigo continua
disponivel para rollback e nao participa deste caminho. Nenhum passo abaixo
foi executado em Production.

| Variavel | Classe no cutover CRM | Uso |
| --- | --- | --- |
| `ORGANIZATION_CONFIG_SOURCE` | STILL_REQUIRED | Gate global `supabase` (padrao), `env` ou `hybrid`; nunca valor por cliente |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | STILL_REQUIRED | Acesso server-side a config, RAG e RPC Vault da base IA |
| `CRM_DISPATCH_SERVICE_TOKEN` | STILL_REQUIRED | Autenticacao global do endpoint privado CRM |
| `OPENAI_RESPONSES_MODEL`, `OPENAI_REASONING_EFFORT` | STILL_REQUIRED / global opcional | Modelo e esforco globais; schema atual nao oferece override por cliente |
| `ORGANIZATION_RUNTIME_CONFIG_JSON` | LEGACY_ONLY | Fonte `env` e fallback explicito `hybrid` apenas quando a organizacao nao existe no Supabase |
| `ORGANIZATION_CREDENTIALS_JSON` | LEGACY_ONLY | Credencial OpenAI para organizacao originada de `env`; nao entra no caminho Supabase |
| `OPENAI_API_KEY` | LEGACY_ONLY | Fallback do adapter antigo e outros fluxos sandbox; o dispatch CRM Supabase nao o utiliza |
| `OPENAI_API_KEY_<cliente>` | LEGACY_ONLY / SAFE_TO_REMOVE_LATER | Refs do mapa de credenciais antigo, somente depois da migracao de seus consumidores |
| `ZAPI_INSTANCE_ID`, `ZAPI_INSTANCE_TOKEN`, `ZAPI_CLIENT_TOKEN` | LEGACY_ONLY / SAFE_TO_REMOVE_LATER | Adapter Z-API antigo; nunca entram no dispatch CRM |
| `ZAPI_INSTANCE_ORGANIZATION_MAP_JSON` | LEGACY_ONLY / SAFE_TO_REMOVE_LATER | Resolucao de tenant do adapter antigo; o CRM fornece `organizationId` ao endpoint novo |

Nao ha variavel por cliente no caminho `supabase`. `hybrid` e uma flag de
rollout: consulta Supabase primeiro; so usa env se a linha da organizacao
estiver ausente. Config ausente/inativa, org inativa, erro de transporte ou
credencial Vault ausente rejeitam sem fallback. A migracao para `supabase`
requer que o mesmo projeto Supabase contenha config, credencial e KB de cada
organizacao. `CRM_SUPABASE_*` pertence ao adapter legado de monitoramento e
nao substitui `SUPABASE_*` deste endpoint.

## Cadastro de cliente depois do cutover

1. Criar/confirmar `organizations` ativa no Supabase da IA com o mesmo UUID
   autenticado que o CRM enviara.
2. Criar `organization_ai_configs` ativa, com `assistant_name` e os campos
   institucionais/comerciais aplicaveis.
3. Criar a API key do OpenAI Project do cliente fora deste repositorio e
   salva-la no Supabase Vault com nome unico `openai:<organization_id>`.
   Anotar apenas o UUID da secret.
4. Criar `organization_credentials` ativa com `provider='OPENAI'` e
   `credential_ref='vault:<uuid>'` da secret. Nao copiar a chave para a linha.
5. Publicar a base de conhecimento da organizacao com versoes `PUBLISHED` e
   `processing_valid=true`; se nao houver KB, a busca retorna vazio sem
   consultar outra organizacao.
6. Validar, em staging e sem imprimir o resultado da RPC, que service_role
   pode resolver a propria ref e que `anon`/`authenticated` nao podem executar
   a funcao; uma ref de A inserida na linha de B deve retornar vazio. Enviar
   dispatch de teste com `organizationId` desse cliente e
   conferir somente decisao e logs sanitizados.

Adicionar B depois de A muda apenas linhas do banco, Vault e KB; nao muda
codigo, env nem deploy. Em modo `supabase`, falta de qualquer requisito fecha
o caminho com `RUNTIME_UNAVAILABLE` para o CRM.

## Gate antes do ambiente alvo

- Revisar/aplicar a migration local `202609290001_ai_organization_openai_vault.sql`
  no ambiente de homologacao; este trabalho nao aplicou migration remota.
- Confirmar Vault habilitado e grants da RPC, inclusive negacao de
  `anon`/`authenticated`, com teste de integracao no Supabase real de staging.
- Migrar clientes existentes para linhas/refs Vault antes de mudar o modo
  global para `supabase`; manter `env`/`hybrid` apenas no periodo de rollback.
- Validar integracao CRM → IA, RAG, OpenAI Project de teste, observabilidade
  e ausencia de secrets em logs. O modelo/reasoning continua global.
