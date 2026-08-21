create extension if not exists vector;

create table if not exists organizations (
  id uuid primary key,
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists documents (
  id uuid primary key,
  organization_id uuid not null references organizations(id),
  document_type text not null,
  title text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id)
);

create table if not exists document_versions (
  id uuid primary key,
  organization_id uuid not null,
  document_id uuid not null,
  version_number integer not null,
  status text not null,
  effective_from timestamptz,
  effective_until timestamptz,
  processing_valid boolean not null default false,
  knowledge_mode text not null default 'OPEN_WORLD',
  closed_world_completeness_approved boolean not null default false,
  approved_by text,
  approved_at timestamptz,
  published_by text,
  published_at timestamptz,
  supersedes_version_id uuid,
  created_at timestamptz not null default now(),
  foreign key (organization_id, document_id) references documents(organization_id, id),
  unique (organization_id, id),
  unique (organization_id, document_id, version_number),
  check (status in ('DRAFT', 'PROCESSING', 'PROCESSING_FAILED', 'REVIEW_REQUIRED', 'APPROVED', 'PUBLISHED', 'SUPERSEDED', 'INACTIVE')),
  check (knowledge_mode in ('OPEN_WORLD', 'CLOSED_WORLD')),
  check (effective_until is null or effective_from is null or effective_until >= effective_from)
);

create table if not exists chunks (
  id uuid primary key,
  organization_id uuid not null,
  document_id uuid not null,
  document_version_id uuid not null,
  chunk_index integer not null,
  content text not null,
  section_path text[] not null,
  semantic_type text,
  metadata jsonb not null default '{}'::jsonb,
  parent_chunk_id uuid,
  source_start_offset integer,
  source_end_offset integer,
  chunking_strategy text not null,
  chunking_version text not null,
  created_at timestamptz not null default now(),
  foreign key (organization_id, document_id) references documents(organization_id, id),
  foreign key (organization_id, document_version_id) references document_versions(organization_id, id),
  unique (organization_id, id),
  check (source_end_offset is null or source_start_offset is null or source_end_offset >= source_start_offset)
);

create table if not exists retrieval_index_entries (
  id uuid primary key,
  organization_id uuid not null,
  chunk_id uuid not null,
  document_id uuid not null,
  document_version_id uuid not null,
  embedding vector(1536),
  embedding_model text not null,
  embedding_version text not null,
  indexed_at timestamptz not null,
  metadata jsonb not null default '{}'::jsonb,
  foreign key (organization_id, chunk_id) references chunks(organization_id, id),
  foreign key (organization_id, document_version_id) references document_versions(organization_id, id),
  unique (organization_id, id)
);

create index if not exists retrieval_index_entries_embedding_idx
  on retrieval_index_entries using ivfflat (embedding vector_cosine_ops);

create table if not exists conversations (
  id uuid primary key,
  organization_id uuid not null references organizations(id),
  channel text not null default 'runtime',
  status text not null,
  current_stage text,
  current_intent text,
  ai_control_active boolean not null default true,
  handoff_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id)
);

create table if not exists conversation_messages (
  id uuid primary key,
  organization_id uuid not null,
  conversation_id uuid not null,
  direction text not null,
  sender_type text not null,
  content text not null,
  created_at timestamptz not null default now(),
  foreign key (organization_id, conversation_id) references conversations(organization_id, id),
  check (direction in ('inbound', 'outbound')),
  check (sender_type in ('patient', 'assistant', 'human', 'system'))
);

create table if not exists operational_audit_events (
  id uuid primary key,
  organization_id uuid not null references organizations(id),
  conversation_id uuid,
  intent text,
  decision text,
  tool_called text,
  document_versions_used uuid[] not null default '{}',
  grounding_result text,
  handoff_reason text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  foreign key (organization_id, conversation_id) references conversations(organization_id, id)
);

create index if not exists chunks_org_version_idx on chunks(organization_id, document_version_id);
create index if not exists document_versions_retrieval_idx
  on document_versions(organization_id, status, processing_valid, effective_from, effective_until);
create index if not exists audit_org_conversation_idx on operational_audit_events(organization_id, conversation_id);
