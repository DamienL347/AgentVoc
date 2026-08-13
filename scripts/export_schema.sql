-- ─────────────────────────────────────────────────────────────────────────────
-- AgentLumy — Export du schéma sans mot de passe Postgres
--
-- Pourquoi : le schéma des tables n'existe que dans Supabase (les .sql d'origine
-- n'ont jamais été commités). Cette requête le reconstitue en DDL.
--
-- MODE D'EMPLOI
--   1. Supabase Dashboard → SQL Editor → New query
--   2. Coller TOUT ce fichier, puis Run
--   3. Le résultat est une seule cellule « ddl » → bouton « Download CSV »
--   4. venv\Scripts\python.exe scripts/csv_to_schema.py <fichier.csv>
--      → écrit scripts/schema.sql, propre et versionnable
--
-- Alternative : si tu as le mot de passe Postgres, scripts/dump_schema.py fait
-- la même chose en une commande.
-- ─────────────────────────────────────────────────────────────────────────────

with cols as (
    select c.oid, c.relname,
           string_agg(
               format('    %I %s%s%s',
                      a.attname,
                      format_type(a.atttypid, a.atttypmod),
                      coalesce(' DEFAULT ' || pg_get_expr(d.adbin, d.adrelid), ''),
                      case when a.attnotnull then ' NOT NULL' else '' end),
               E',\n' order by a.attnum) as coldef
    from pg_class c
    join pg_namespace n  on n.oid = c.relnamespace
    join pg_attribute a  on a.attrelid = c.oid
    left join pg_attrdef d on d.adrelid = c.oid and d.adnum = a.attnum
    where n.nspname = 'public' and c.relkind = 'r'
      and a.attnum > 0 and not a.attisdropped
    group by c.oid, c.relname
),
cons as (
    select conrelid as oid,
           string_agg(format('    CONSTRAINT %I %s', conname, pg_get_constraintdef(oid)),
                      E',\n' order by contype desc, conname) as condef
    from pg_constraint
    where connamespace = 'public'::regnamespace
    group by conrelid
),
parts as (
    -- En-tête
    select 0 as ord, '' as name,
           E'-- AgentLumy — Schéma Supabase (export SQL Editor)\n'
           '-- NE PAS ÉDITER À LA MAIN : modifier la base puis relancer l''export.' as stmt

    -- Types énumérés
    union all select 10, '', E'\n-- ============================ TYPES ÉNUMÉRÉS ============================'
    union all
    select 11, t.typname,
           format('CREATE TYPE public.%I AS ENUM (%s);', t.typname,
                  string_agg(quote_literal(e.enumlabel), ', ' order by e.enumsortorder))
    from pg_type t
    join pg_enum e      on e.enumtypid = t.oid
    join pg_namespace n on n.oid = t.typnamespace
    where n.nspname = 'public'
    group by t.typname

    -- Tables
    union all select 20, '', E'\n-- ================================ TABLES ================================'
    union all
    select 21, cols.relname,
           format(E'\nCREATE TABLE public.%I (\n%s\n);', cols.relname,
                  cols.coldef || coalesce(E',\n' || cons.condef, ''))
    from cols left join cons on cons.oid = cols.oid

    -- Index (hors ceux créés par une contrainte)
    union all select 30, '', E'\n-- ================================ INDEX ================================='
    union all
    select 31, indexname, indexdef || ';'
    from pg_indexes
    where schemaname = 'public'
      and indexname not in (
          select conname from pg_constraint where connamespace = 'public'::regnamespace
      )

    -- Fonctions (hors fonctions apportées par une extension)
    union all select 40, '', E'\n-- ============================== FONCTIONS ==============================='
    union all
    select 41, p.proname, pg_get_functiondef(p.oid) || E';\n'
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.prokind = 'f'
      and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')

    -- Triggers
    union all select 50, '', E'\n-- =============================== TRIGGERS ==============================='
    union all
    select 51, t.tgname, pg_get_triggerdef(t.oid) || ';'
    from pg_trigger t
    join pg_class c     on c.oid = t.tgrelid
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and not t.tgisinternal

    -- Vues
    union all select 60, '', E'\n-- ================================ VUES =================================='
    union all
    select 61, c.relname,
           format(E'CREATE OR REPLACE VIEW public.%I AS\n%s', c.relname,
                  pg_get_viewdef(c.oid, true))
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'v'

    -- Row Level Security
    union all select 70, '', E'\n-- ========================= ROW LEVEL SECURITY ==========================='
    union all
    select 71, c.relname,
           format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', c.relname)
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'r' and c.relrowsecurity

    union all
    select 72, pol.polname,
           'CREATE POLICY ' || quote_ident(pol.polname) || ' ON public.' || quote_ident(c.relname)
           || ' FOR ' || case pol.polcmd
                             when 'r' then 'SELECT' when 'a' then 'INSERT'
                             when 'w' then 'UPDATE' when 'd' then 'DELETE'
                             else 'ALL' end
           || coalesce(' TO ' || (select string_agg(rolname, ', ')
                                  from pg_roles where oid = any(pol.polroles)), '')
           || coalesce(E'\n    USING (' || pg_get_expr(pol.polqual, pol.polrelid) || ')', '')
           || coalesce(E'\n    WITH CHECK (' || pg_get_expr(pol.polwithcheck, pol.polrelid) || ')', '')
           || ';'
    from pg_policy pol
    join pg_class c     on c.oid = pol.polrelid
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
)
select string_agg(stmt, E'\n' order by ord, name) as ddl
from parts;
