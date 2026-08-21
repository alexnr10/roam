-- Bouchons Supabase pour valider le schéma sur un PostgreSQL nu.
-- À charger AVANT db/schema.sql en local. Ne jamais exécuter sur Supabase :
-- `auth.uid()` y est déjà fourni par la plateforme.

create schema if not exists auth;

create table if not exists auth.users (
  id uuid primary key default gen_random_uuid()
);

create or replace function auth.uid() returns uuid
language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;
