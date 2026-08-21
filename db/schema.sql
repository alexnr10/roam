-- Roam — schéma de base (PostgreSQL + PostGIS, cible Supabase)
-- Convention : tout est en anglais dans le code, en français dans le contenu.

create extension if not exists postgis;
create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Types
-- ---------------------------------------------------------------------------

create type place_status      as enum ('draft', 'published', 'archived', 'rejected');
create type collection_kind   as enum ('theme', 'geo', 'label');
create type geo_level         as enum ('commune', 'departement', 'region', 'country');
create type checkin_method    as enum ('gps', 'photo', 'declared');
create type feedback_vote     as enum ('promote', 'keep', 'demote', 'remove');
create type submission_status as enum ('pending', 'accepted', 'rejected', 'duplicate');

-- ---------------------------------------------------------------------------
-- Référentiels
-- ---------------------------------------------------------------------------

-- Thèmes : châteaux, cascades, plages… Alimente les collections thématiques.
create table themes (
  id                  text primary key,           -- slug, ex. 'chateaux'
  name                text not null,
  name_singular       text not null,
  icon                text,
  -- rayon de validation par défaut des lieux du thème, en mètres
  default_radius_m    int  not null default 150,
  sort_order          int  not null default 100
);

-- Labels : UNESCO, Grands Sites, Plus Beaux Villages…
-- Sert à la fois de signal de score et de collection dédiée.
create table labels (
  id                  text primary key,           -- slug, ex. 'plus-beaux-villages'
  name                text not null,
  authority           text,                       -- organisme délivrant le label
  url                 text,
  -- bonus appliqué au score d'un lieu portant ce label
  score_bonus         numeric(6,2) not null default 0,
  -- true si le label génère sa propre collection
  makes_collection    boolean not null default true
);

-- Découpage administratif français (communes, départements, régions).
-- `code` = code INSEE pour les communes, code département ('2A', '75'), code région.
create table geo_areas (
  id                  text primary key,           -- ex. 'dept:75', 'region:11', 'commune:75056'
  level               geo_level not null,
  code                text not null,
  name                text not null,
  parent_id           text references geo_areas(id),
  country_code        char(2) not null default 'FR',
  unique (level, code, country_code)
);

create index geo_areas_parent_idx on geo_areas(parent_id);

-- ---------------------------------------------------------------------------
-- Lieux
-- ---------------------------------------------------------------------------

create table places (
  id                  uuid primary key default gen_random_uuid(),
  slug                text unique not null,
  name                text not null,
  theme_id            text not null references themes(id),

  -- Un lieu est TOUJOURS un point. Pour un site étendu (gorges, massif), c'est le
  -- point d'entrée ou le point de vue emblématique ; la taille est portée par le rayon.
  location            geography(Point, 4326) not null,
  validation_radius_m int not null default 150 check (validation_radius_m between 20 and 5000),
  elevation_m         int,

  -- Rattachement administratif (dénormalisé pour les collections géographiques)
  commune_id          text references geo_areas(id),
  departement_id      text references geo_areas(id),
  region_id           text references geo_areas(id),
  country_code        char(2) not null default 'FR',

  -- Éditorial
  summary             text,                       -- 2 phrases : pourquoi ça vaut le détour
  description         text,
  best_season         text,
  access_note         text,                       -- accès, stationnement, réglementation
  cover_image_url     text,
  image_attribution   text,                       -- obligatoire si Wikimedia Commons

  -- Curation
  status              place_status not null default 'draft',
  score               numeric(8,3) not null default 0,
  inclusion_criteria  text[] not null default '{}',   -- 'C1'..'C5', cf. charte
  curator_note        text,
  reviewed_at         timestamptz,
  reviewed_by         uuid,

  -- Provenance
  wikidata_id         text unique,
  wikipedia_url       text,
  commons_category    text,
  sitelink_count      int not null default 0,
  osm_id              text,
  merimee_ref         text,
  source              text not null default 'pipeline',  -- 'pipeline' | 'community' | 'manual'
  submitted_by        uuid,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create index places_location_idx     on places using gist (location);
create index places_theme_idx        on places (theme_id) where status = 'published';
create index places_departement_idx  on places (departement_id) where status = 'published';
create index places_status_score_idx on places (status, score desc);

create table place_labels (
  place_id            uuid not null references places(id) on delete cascade,
  label_id            text not null references labels(id) on delete cascade,
  primary key (place_id, label_id)
);

-- ---------------------------------------------------------------------------
-- Collections
-- ---------------------------------------------------------------------------

create table collections (
  id                  uuid primary key default gen_random_uuid(),
  slug                text unique not null,
  name                text not null,
  kind                collection_kind not null,

  theme_id            text references themes(id),
  label_id            text references labels(id),
  geo_area_id         text references geo_areas(id),

  description         text,
  icon                text,
  cover_image_url     text,
  status              place_status not null default 'draft',

  -- Renseignés par le pipeline, utiles pour l'affichage sans agrégat
  place_count         int not null default 0,
  tier_counts         int[] not null default '{0,0,0}',

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),

  -- Une collection est soit thématique, soit géographique, soit un label,
  -- soit un croisement thème × géographie.
  check (
    (kind = 'theme' and theme_id is not null) or
    (kind = 'label' and label_id is not null) or
    (kind = 'geo'   and geo_area_id is not null)
  )
);

-- Le lien N-N qui fait tout le produit : un lieu compte dans plusieurs collections.
-- `tier` est le niveau du lieu DANS CETTE collection (1 = incontournable).
create table collection_places (
  collection_id       uuid not null references collections(id) on delete cascade,
  place_id            uuid not null references places(id) on delete cascade,
  tier                smallint not null check (tier between 1 and 3),
  rank                int not null,
  primary key (collection_id, place_id)
);

create index collection_places_place_idx on collection_places (place_id);
create index collection_places_tier_idx  on collection_places (collection_id, tier, rank);

-- ---------------------------------------------------------------------------
-- Utilisateurs et visites
-- ---------------------------------------------------------------------------

-- Sur Supabase, `auth.users` fait foi ; cette table porte le profil applicatif.
create table profiles (
  id                  uuid primary key,
  display_name        text,
  avatar_url          text,
  home_location       geography(Point, 4326),
  -- 'local' (week-ends près de chez soi) | 'traveller' | 'both'
  travel_profile      text not null default 'both',
  onboarded_at        timestamptz,
  created_at          timestamptz not null default now()
);

create table check_ins (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references profiles(id) on delete cascade,
  place_id            uuid not null references places(id) on delete cascade,

  method              checkin_method not null,
  -- true seulement si validé par GPS sur place : donne le badge « vérifié »
  verified            boolean not null default false,
  visited_at          timestamptz not null default now(),

  -- Contexte de validation GPS
  gps_accuracy_m      numeric(6,1),
  distance_m          numeric(8,1),
  device_location     geography(Point, 4326),

  photo_url           text,
  note                text,

  created_at          timestamptz not null default now(),
  -- Un lieu ne compte qu'une fois par utilisateur.
  unique (user_id, place_id)
);

create index check_ins_user_idx on check_ins (user_id, visited_at desc);

-- ---------------------------------------------------------------------------
-- Badges
-- ---------------------------------------------------------------------------

create table badges (
  id                  uuid primary key default gen_random_uuid(),
  slug                text unique not null,
  name                text not null,
  description         text,
  icon                text,
  collection_id       uuid references collections(id) on delete cascade,
  -- Débloqué à X % de la collection (paliers : 25, 50, 75, 100)…
  threshold_pct       smallint check (threshold_pct between 1 and 100),
  -- …ou à la complétion d'un niveau donné.
  tier                smallint check (tier between 1 and 3),
  -- true : exige des visites vérifiées au GPS, pas seulement déclarées
  requires_verified   boolean not null default false,
  check (threshold_pct is not null or tier is not null)
);

create table user_badges (
  user_id             uuid not null references profiles(id) on delete cascade,
  badge_id            uuid not null references badges(id) on delete cascade,
  earned_at           timestamptz not null default now(),
  primary key (user_id, badge_id)
);

-- ---------------------------------------------------------------------------
-- Contribution et feedback communautaires
-- ---------------------------------------------------------------------------

create table place_submissions (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references profiles(id) on delete cascade,
  name                text not null,
  theme_id            text references themes(id),
  location            geography(Point, 4326) not null,
  -- Critère d'inclusion revendiqué (C1..C5) et sa source — cf. charte
  claimed_criteria    text[] not null default '{}',
  source_url          text,
  photo_url           text not null,
  rationale           text not null,             -- pourquoi ça vaut le déplacement

  status              submission_status not null default 'pending',
  review_note         text,
  reviewed_at         timestamptz,
  reviewed_by         uuid,
  created_place_id    uuid references places(id),
  created_at          timestamptz not null default now()
);

create index place_submissions_pending_idx on place_submissions (status, created_at);

create table place_feedback (
  user_id             uuid not null references profiles(id) on delete cascade,
  place_id            uuid not null references places(id) on delete cascade,
  vote                feedback_vote not null,
  reason              text,
  created_at          timestamptz not null default now(),
  primary key (user_id, place_id)
);

-- File de revue : uniquement les votes d'utilisateurs qui ont VISITÉ le lieu.
-- Seul quelqu'un qui y est allé peut dire que ça ne valait pas le déplacement ;
-- c'est aussi ce qui rend le brigading coûteux.
create view place_feedback_signal as
select
  f.place_id,
  count(*) filter (where f.vote = 'promote') as promote_count,
  count(*) filter (where f.vote = 'demote')  as demote_count,
  count(*) filter (where f.vote = 'remove')  as remove_count,
  count(*)                                   as total_votes
from place_feedback f
join check_ins c on c.user_id = f.user_id and c.place_id = f.place_id
group by f.place_id;

-- ---------------------------------------------------------------------------
-- Progression
-- ---------------------------------------------------------------------------

create view user_collection_progress as
select
  ci.user_id,
  cp.collection_id,
  count(*)                                                as visited_count,
  count(*) filter (where ci.verified)                     as verified_count,
  count(*) filter (where cp.tier = 1)                     as visited_tier1,
  count(*) filter (where cp.tier = 2)                     as visited_tier2,
  count(*) filter (where cp.tier = 3)                     as visited_tier3,
  c.place_count,
  round(100.0 * count(*) / nullif(c.place_count, 0), 1)   as pct
from check_ins ci
join collection_places cp on cp.place_id = ci.place_id
join collections c        on c.id = cp.collection_id
where c.status = 'published'
group by ci.user_id, cp.collection_id, c.place_count;

-- ---------------------------------------------------------------------------
-- Row Level Security (Supabase)
-- ---------------------------------------------------------------------------

alter table places             enable row level security;
alter table collections        enable row level security;
alter table collection_places  enable row level security;
alter table profiles           enable row level security;
alter table check_ins          enable row level security;
alter table user_badges        enable row level security;
alter table place_submissions  enable row level security;
alter table place_feedback     enable row level security;

-- Catalogue : lecture publique du contenu publié uniquement.
create policy "published places are readable"
  on places for select using (status = 'published');
create policy "published collections are readable"
  on collections for select using (status = 'published');
create policy "collection places are readable"
  on collection_places for select using (true);

-- Données personnelles : chacun ne voit et n'écrit que les siennes.
create policy "own profile" on profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);
create policy "own check-ins" on check_ins
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own badges" on user_badges
  for select using (auth.uid() = user_id);
create policy "own submissions" on place_submissions
  for select using (auth.uid() = user_id);
create policy "submit a place" on place_submissions
  for insert with check (auth.uid() = user_id);
create policy "own feedback" on place_feedback
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- NOTE monétisation : le catalogue n'est jamais servi en masse au client.
-- L'app interroge par emprise de carte via une fonction RPC bornée, pas par
-- un `select *` sur `places`.
