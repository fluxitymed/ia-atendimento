-- Apply only after Supabase Vault is enabled and reviewed in the target environment.
-- The public table stores only vault:<uuid>; plaintext exists only in Vault and
-- the service-role response to this narrowly scoped RPC.
begin;

create or replace function public.resolve_organization_openai_credential(
  p_organization_id uuid
)
returns table (organization_id uuid, credential_ref text, secret text)
language sql
stable
security definer
set search_path = ''
as $$
  select c.organization_id, c.credential_ref, v.decrypted_secret
  from public.organization_credentials as c
  join vault.decrypted_secrets as v
    on c.credential_ref = 'vault:' || v.id::text
  where c.organization_id = p_organization_id
    and c.provider = 'OPENAI'
    and c.status = 'active'
    and v.name = 'openai:' || p_organization_id::text
    and v.decrypted_secret is not null
  limit 2
$$;

revoke all on function public.resolve_organization_openai_credential(uuid)
  from public, anon, authenticated;
grant execute on function public.resolve_organization_openai_credential(uuid)
  to service_role;

commit;
