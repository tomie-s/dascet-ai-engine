create extension if not exists vector with schema extensions;

create table if not exists public.financial_tools (
  id uuid primary key,
  name text not null,
  tagline text not null,
  logo_url text,
  learn_more_url text,
  category text[] not null default '{}',
  user_type text,
  platform_type text[] not null default '{}',
  experience_level text,
  pricing_model text,
  free_tier boolean,
  country_origin text,
  canadian_available boolean not null default false,
  canadian_available_notes text,
  average_rating numeric,
  total_ratings integer,
  status text not null,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  logo_fetched_at timestamptz,
  slug text,
  description text,
  complexity_level integer,
  monthly_cost numeric,
  target_situations text[] not null default '{}',
  friction_tags text[] not null default '{}',
  key_features text[] not null default '{}',
  dascet_tags text[] not null default '{}',
  pricing_plain text,
  toolkit_save_count integer not null default 0,
  wishlist_save_count integer not null default 0,
  bayesian_rating numeric,
  embedding extensions.vector(512)
);

create index if not exists financial_tools_status_idx
  on public.financial_tools (status);

create index if not exists financial_tools_embedding_hnsw_idx
  on public.financial_tools
  using hnsw (embedding extensions.vector_cosine_ops)
  where embedding is not null;

alter table public.financial_tools enable row level security;

create or replace function public.match_financial_tools(
  query_embedding extensions.vector(512),
  match_threshold double precision default 0.45,
  match_count integer default 5
)
returns table (
  id uuid,
  name text,
  tagline text,
  category text[],
  canadian_available boolean,
  similarity double precision
)
language sql
stable
security invoker
set search_path = ''
as $$
  select
    tool.id,
    tool.name,
    tool.tagline,
    tool.category,
    tool.canadian_available,
    1 - (tool.embedding OPERATOR(extensions.<=>) query_embedding) as similarity
  from public.financial_tools as tool
  where tool.status = 'approved'
    and tool.embedding is not null
    and 1 - (tool.embedding OPERATOR(extensions.<=>) query_embedding) >= match_threshold
  order by tool.embedding OPERATOR(extensions.<=>) query_embedding
  limit greatest(match_count, 0);
$$;

revoke all on function public.match_financial_tools(
  extensions.vector,
  double precision,
  integer
) from public;

grant execute on function public.match_financial_tools(
  extensions.vector,
  double precision,
  integer
) to service_role;
