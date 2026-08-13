"""
Exporte le schéma de la base Supabase vers scripts/schema.sql (versionnable dans Git).

Pourquoi ce script existe : le schéma des 10 tables n'existait qu'à l'intérieur de
Supabase (les .sql d'origine n'ont jamais été commités). Un projet gratuit mis en pause
ou supprimé, et tout le modèle de données disparaît.

Usage :
    venv\\Scripts\\python.exe scripts/dump_schema.py

Nécessite dans .env :
    SUPABASE_DB_PASSWORD=<mot de passe Postgres>
        → Supabase Dashboard > Project Settings > Database > Database password
          (« Reset database password » si tu ne l'as plus)

Note : le host direct db.<ref>.supabase.co est en IPv6 uniquement. Si ta connexion
n'a pas d'IPv6, utilise la chaîne « Session pooler » (IPv4) proposée par Supabase
et renseigne SUPABASE_DB_HOST / SUPABASE_DB_USER en conséquence.
"""
import os
import re
import sys
from datetime import date
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "scripts" / "schema.sql"


def get_connection():
    load_dotenv(ROOT / ".env")

    password = os.getenv("SUPABASE_DB_PASSWORD")
    host     = os.getenv("SUPABASE_DB_HOST")
    user     = os.getenv("SUPABASE_DB_USER", "postgres")

    # À défaut, on tente d'extraire host/user de DATABASE_URL (le mot de passe y est
    # souvent invalide car non URL-encodé : on ne s'y fie pas).
    if not host:
        dsn = os.getenv("DATABASE_URL", "")
        m   = re.match(r"postgresql://([^:]+):(.*)@([^@/]+):(\d+)/(\w+)$", dsn)
        if not m:
            sys.exit("[ERREUR] Impossible de determiner le host : renseigne SUPABASE_DB_HOST dans .env")
        user, pwd_from_dsn, host, _, _ = m.groups()
        password = password or pwd_from_dsn

    if not password:
        sys.exit("[ERREUR] SUPABASE_DB_PASSWORD manquant dans .env")

    return psycopg2.connect(
        host=host, port=int(os.getenv("SUPABASE_DB_PORT", "5432")),
        user=user, password=password, dbname="postgres",
        sslmode="require", connect_timeout=20,
    )


# ── Requêtes d'introspection ─────────────────────────────────────────────────

Q_ENUMS = """
select t.typname,
       string_agg(quote_literal(e.enumlabel), ', ' order by e.enumsortorder)
from pg_type t
join pg_enum e on e.enumtypid = t.oid
join pg_namespace n on n.oid = t.typnamespace
where n.nspname = 'public'
group by t.typname order by t.typname;
"""

Q_TABLES = """
select c.relname
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by c.relname;
"""

Q_COLUMNS = """
select a.attname,
       format_type(a.atttypid, a.atttypmod),
       a.attnotnull,
       pg_get_expr(d.adbin, d.adrelid)
from pg_attribute a
left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
where a.attrelid = %s::regclass and a.attnum > 0 and not a.attisdropped
order by a.attnum;
"""

Q_CONSTRAINTS = """
select conname, pg_get_constraintdef(oid)
from pg_constraint
where conrelid = %s::regclass
order by contype desc, conname;
"""

Q_INDEXES = """
select indexdef from pg_indexes
where schemaname = 'public' and tablename = %s
  and indexname not in (
      select conname from pg_constraint where conrelid = ('public.' || %s)::regclass
  )
order by indexname;
"""

Q_TRIGGERS = """
select pg_get_triggerdef(t.oid)
from pg_trigger t
where t.tgrelid = %s::regclass and not t.tgisinternal
order by t.tgname;
"""

Q_POLICIES = """
select polname,
       case polcmd when 'r' then 'SELECT' when 'a' then 'INSERT'
                   when 'w' then 'UPDATE' when 'd' then 'DELETE' else 'ALL' end,
       pg_get_expr(polqual, polrelid),
       pg_get_expr(polwithcheck, polrelid),
       (select string_agg(rolname, ', ') from pg_roles where oid = any(polroles))
from pg_policy where polrelid = %s::regclass order by polname;
"""

Q_RLS_ENABLED = """
select relrowsecurity from pg_class where oid = %s::regclass;
"""

Q_FUNCTIONS = """
select pg_get_functiondef(p.oid)
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.prokind = 'f'
order by p.proname;
"""

Q_VIEWS = """
select c.relname, pg_get_viewdef(c.oid, true)
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'v'
order by c.relname;
"""


def main():
    conn = get_connection()
    cur  = conn.cursor()
    out  = []

    def section(title):
        out.append(f"\n-- {'=' * 74}\n-- {title}\n-- {'=' * 74}\n")

    out.append("-- ─────────────────────────────────────────────────────────────────────")
    out.append("-- AgentLumy — Schéma Supabase (export automatique)")
    out.append(f"-- Généré le {date.today().strftime('%d/%m/%Y')} par scripts/dump_schema.py")
    out.append("-- NE PAS ÉDITER À LA MAIN : modifier la base puis relancer le script.")
    out.append("-- ─────────────────────────────────────────────────────────────────────")

    # ENUMs
    section("TYPES ÉNUMÉRÉS")
    cur.execute(Q_ENUMS)
    for name, labels in cur.fetchall():
        out.append(f"CREATE TYPE public.{name} AS ENUM ({labels});")

    # Tables
    cur.execute(Q_TABLES)
    tables = [r[0] for r in cur.fetchall()]

    section("TABLES")
    for t in tables:
        qualified = f"public.{t}"
        cur.execute(Q_COLUMNS, (qualified,))
        cols = []
        for name, typ, notnull, default in cur.fetchall():
            line = f"    {name} {typ}"
            if default:
                line += f" DEFAULT {default}"
            if notnull:
                line += " NOT NULL"
            cols.append(line)

        cur.execute(Q_CONSTRAINTS, (qualified,))
        constraints = [f"    CONSTRAINT {n} {d}" for n, d in cur.fetchall()]

        out.append(f"\nCREATE TABLE {qualified} (")
        out.append(",\n".join(cols + constraints))
        out.append(");")

    # Index
    section("INDEX")
    for t in tables:
        cur.execute(Q_INDEXES, (t, t))
        for (idxdef,) in cur.fetchall():
            out.append(f"{idxdef};")

    # Fonctions
    section("FONCTIONS")
    cur.execute(Q_FUNCTIONS)
    for (fndef,) in cur.fetchall():
        out.append(f"{fndef};\n")

    # Triggers
    section("TRIGGERS")
    for t in tables:
        cur.execute(Q_TRIGGERS, (f"public.{t}",))
        for (trgdef,) in cur.fetchall():
            out.append(f"{trgdef};")

    # Vues
    section("VUES")
    cur.execute(Q_VIEWS)
    for name, viewdef in cur.fetchall():
        out.append(f"CREATE OR REPLACE VIEW public.{name} AS\n{viewdef}\n")

    # RLS
    section("ROW LEVEL SECURITY")
    for t in tables:
        qualified = f"public.{t}"
        cur.execute(Q_RLS_ENABLED, (qualified,))
        if cur.fetchone()[0]:
            out.append(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY;")
        cur.execute(Q_POLICIES, (qualified,))
        for polname, cmd, qual, withcheck, roles in cur.fetchall():
            stmt = f'CREATE POLICY "{polname}" ON {qualified}\n    FOR {cmd}'
            if roles:
                stmt += f"\n    TO {roles}"
            if qual:
                stmt += f"\n    USING ({qual})"
            if withcheck:
                stmt += f"\n    WITH CHECK ({withcheck})"
            out.append(stmt + ";")

    conn.close()

    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"[OK] Schema exporte : {OUT}")
    print(f"   {len(tables)} tables, {OUT.stat().st_size} octets")


if __name__ == "__main__":
    main()
