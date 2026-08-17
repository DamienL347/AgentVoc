"""
Envoi des rappels de RDV — a la main ou par un ordonnanceur local.

En production, c'est Cloud Scheduler qui appelle POST /internal/reminders/run
(voir docs/DEPLOIEMENT.md). Ce script sert avant le deploiement, et pour
verifier ce qui PARTIRAIT sans rien envoyer.

Usage :
    venv\\Scripts\\python.exe scripts/send_reminders.py --dry-run
    venv\\Scripts\\python.exe scripts/send_reminders.py
    venv\\Scripts\\python.exe scripts/send_reminders.py --ignorer-heures

Avec PROVIDER_MODE=fake, aucun SMS ne part reellement : les envois sont
journalises et traces en base comme s'ils avaient eu lieu.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv   # noqa: E402
load_dotenv()

from app.config import settings                              # noqa: E402
from app.services.reminder_service import (                   # noqa: E402
    STATUTS_ACTIFS,
    ReminderService,
    reminder_service,
)


def lister_a_venir() -> None:
    """Ce qui partirait, sans rien envoyer."""
    from app.db.supabase_client import get_supabase_client

    db  = get_supabase_client()
    now = datetime.now(timezone.utc)

    print(f"\nRendez-vous actifs dans les 48 h (a {now.astimezone().strftime('%d/%m %H:%M')})\n")

    rdvs = (
        db.table("appointments")
        .select("id, client_name, client_phone, scheduled_at, title, status, "
                "reminder_24h_sent, reminder_2h_sent")
        .in_("status", list(STATUTS_ACTIFS))
        .gte("scheduled_at", now.isoformat())
        .lte("scheduled_at", (now + timedelta(hours=48)).isoformat())
        .order("scheduled_at")
        .execute()
    ).data or []

    if not rdvs:
        print("  (aucun)")
        return

    for r in rdvs:
        prevu = datetime.fromisoformat(str(r["scheduled_at"]).replace("Z", "+00:00"))
        dans  = (prevu - now).total_seconds() / 3600
        j1    = "envoye" if r["reminder_24h_sent"] else "a envoyer"
        h2    = "envoye" if r["reminder_2h_sent"]  else "a envoyer"
        print(f"  {prevu.astimezone().strftime('%d/%m %H:%M')} "
              f"(dans {dans:4.1f} h) | {(r.get('client_name') or '?')[:22]:22} "
              f"| {r.get('client_phone') or 'SANS NUMERO':15} "
              f"| J-1 {j1:9} | H-2 {h2}")

    print(f"\n  {len(rdvs)} rendez-vous")


async def envoyer(ignorer_heures: bool) -> None:
    mode = "SIMULE (aucun SMS reel)" if settings.use_fake_providers else "REEL"
    print(f"\nMode fournisseurs : {mode}")

    bilan = await reminder_service.run(ignorer_heures=ignorer_heures)

    if bilan.get("differe"):
        print("\n  Envois differes : hors de la plage 8h-20h.")
        print("  Utiliser --ignorer-heures pour forcer (tests uniquement).")
        return

    print(f"\n  Envoyes : {bilan['envoyes']}")
    print(f"  Echecs  : {bilan['echecs']}")
    print(f"  Ignores : {bilan['ignores']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rappels de rendez-vous AgentLumy")
    parser.add_argument("--dry-run", action="store_true",
                        help="liste les RDV a venir sans rien envoyer")
    parser.add_argument("--ignorer-heures", action="store_true",
                        help="forcer l'envoi hors 8h-20h (tests uniquement)")
    args = parser.parse_args()

    if args.dry_run:
        lister_a_venir()
        return

    asyncio.run(envoyer(args.ignorer_heures))


if __name__ == "__main__":
    main()
