create table if not exists organizations (
  id uuid primary key,
  name text not null,
  created_at timestamptz not null default now()
);

alter table organizations add column if not exists slug text;
alter table organizations add column if not exists status text not null default 'active';
alter table organizations add column if not exists updated_at timestamptz not null default now();

create unique index if not exists organizations_slug_unique_idx
  on organizations(slug)
  where slug is not null;

create table if not exists organization_ai_configs (
  organization_id uuid primary key references organizations(id) on delete cascade,
  assistant_name text,
  assistant_role text,
  clinic_name text,
  doctor_name text,
  sales_goal text not null default 'conduzir o paciente ate o proximo passo adequado',
  primary_conversion_action text not null default 'avaliacao ou consulta',
  max_discovery_depth integer not null default 3,
  cta_style text not null default 'natural e sem pressao',
  appointment_flow text not null default 'somente quando contexto de agendamento estiver ativo',
  business_hours text,
  locations text[] not null default '{}',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (max_discovery_depth >= 0),
  check (status in ('active', 'inactive', 'suspended'))
);

create table if not exists organization_integrations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  provider text not null,
  provider_account_id text not null,
  status text not null default 'active',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, provider_account_id),
  unique (organization_id, provider, provider_account_id),
  check (status in ('active', 'inactive', 'suspended'))
);

create table if not exists organization_credentials (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  provider text not null,
  credential_ref text not null,
  status text not null default 'active',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, provider, credential_ref),
  check (status in ('active', 'inactive', 'suspended'))
);

create table if not exists ai_usage_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  conversation_id uuid,
  provider text not null,
  model text not null,
  provider_request_id text,
  input_tokens integer,
  output_tokens integer,
  total_tokens integer,
  estimated_cost_usd numeric(12, 6),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (input_tokens is null or input_tokens >= 0),
  check (output_tokens is null or output_tokens >= 0),
  check (total_tokens is null or total_tokens >= 0)
);

create unique index if not exists ai_usage_events_provider_request_unique_idx
  on ai_usage_events(provider, provider_request_id);

create index if not exists organization_integrations_org_provider_idx
  on organization_integrations(organization_id, provider, status);

create index if not exists organization_credentials_org_provider_idx
  on organization_credentials(organization_id, provider, status);

create index if not exists ai_usage_events_org_created_idx
  on ai_usage_events(organization_id, created_at desc);
