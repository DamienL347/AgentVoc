"""
Outils RGPD — purge des donnees echues et droit a l'effacement.

En production, la purge est declenchee par Cloud Scheduler
(POST /internal/retention/run). Ce script sert avant le deploiement, et pour
repondre a une demande d'effacement d'un client.

Usage :
    # Voir ce qui serait purge, sans rien modifier
    venv\\Scripts\\python.exe scripts/rgpd.py purge --dry-run
    venv\\Scripts\\python.exe scripts/rgpd.py purge

    # Droit a l'effacement (RGPD art. 17) pour une personne
    venv\\Scripts\\python.exe scripts/rgpd.py effacer +33612345678 --dry-run
    venv\\Scripts\\python.exe scripts/rgpd.py effacer +33612345678

    # Ce qui est actuellement detenu
    venv\\Scripts\\python.exe scripts/rgpd.py inventaire
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv   # noqa: E402
load_dotenv()

from app.config import settings                                  # noqa: E402
from app.services.retention_service import (                      # noqa: E402
    ANONYME,
    retention_service,
)


def afficher_durees() -> None:
    print("\nDurees de conservation configurees (.env)")
    print(f"  enregistrements audio : {settings.RETENTION_RECORDINGS_DAYS} j")
    print(f"  transcriptions        : {settings.RETENTION_TRANSCRIPTS_DAYS} j")
    print(f"  n° appelant + resume  : {settings.RETENTION_CALL_DETAILS_DAYS} j")
    print(f"  contenu SMS/emails    : {settings.RETENTION_NOTIFICATIONS_DAYS} j")
    print(f"  clients inactifs      : {settings.RETENTION_INACTIVE_CLIENTS_DAYS} j")


def inventaire() -> None:
    """Ce qui est detenu aujourd'hui — utile pour le registre des traitements."""
    from app.db.supabase_client import get_supabase_client
    db = get_supabase_client()

    def compter(table: str) -> int:
        return db.table(table).select("id", count="exact").execute().count

    audio = db.table("calls").select("id", count="exact") \
              .not_.is_("recording_url", "null").execute().count
    transcrits = db.table("calls").select("id", count="exact") \
                   .not_.is_("transcription", "null").execute().count
    anonymises = db.table("calls").select("id", count="exact") \
                   .eq("caller_phone", ANONYME).execute().count

    print("\nDonnees personnelles actuellement detenues\n")
    print(f"  appels enregistres          : {compter('calls')}")
    print(f"    dont audio conserve       : {audio}")
    print(f"    dont transcription        : {transcrits}")
    print(f"    deja anonymises           : {anonymises}")
    print(f"  fiches clients finaux       : {compter('end_clients')}")
    print(f"  rendez-vous                 : {compter('appointments')}")
    print(f"  notifications               : {compter('notifications')}")

    afficher_durees()


async def purger(dry_run: bool) -> None:
    afficher_durees()
    bilan = await retention_service.run(dry_run=dry_run)

    entete = "A PURGER (aucune modification)" if dry_run else "PURGE EFFECTUEE"
    print(f"\n{entete}\n")
    print(f"  enregistrements audio : {bilan['enregistrements']}")
    print(f"  transcriptions        : {bilan['transcriptions']}")
    print(f"  appels anonymises     : {bilan['appels']}")
    print(f"  notifications         : {bilan['notifications']}")
    print(f"  clients supprimes     : {bilan['clients']}")

    if dry_run:
        print("\n  Relancer sans --dry-run pour appliquer.")
    print()


async def effacer(telephone: str, garage_id: str | None,
                  tous_garages: bool, dry_run: bool) -> None:
    bilan = await retention_service.effacer_personne(
        telephone, garage_id=garage_id, tous_garages=tous_garages, dry_run=dry_run,
    )

    if "erreur" in bilan:
        print(f"\n  {bilan['erreur']}\n")
        sys.exit(1)

    entete = "SERAIT EFFACE (aucune modification)" if dry_run else "EFFACEMENT EFFECTUE"
    print(f"\n{entete} — {bilan['telephone']}\n")
    print(f"  appels anonymises   : {bilan['appels']}")
    print(f"  rendez-vous         : {bilan['rendez_vous']}")
    print(f"  notifications       : {bilan['notifications']}")
    print(f"  fiches client       : {bilan['fiches_client']}")

    if dry_run:
        print("\n  Relancer sans --dry-run pour appliquer.")
    else:
        print("\n  Conserver la trace de la demande : l'article 12 impose de")
        print("  pouvoir justifier la reponse apportee a la personne.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Outils RGPD AgentLumy")
    sous = parser.add_subparsers(dest="commande", required=True)

    p_purge = sous.add_parser("purge", help="applique les durees de conservation")
    p_purge.add_argument("--dry-run", action="store_true")

    p_eff = sous.add_parser("effacer", help="droit a l'effacement pour un numero")
    p_eff.add_argument("telephone")
    p_eff.add_argument("--garage", default=None,
                       help="id du garage qui porte la demande (requis)")
    p_eff.add_argument("--tous-garages", action="store_true",
                       help="demande adressee a la plateforme, tous garages confondus")
    p_eff.add_argument("--dry-run", action="store_true")

    sous.add_parser("inventaire", help="ce qui est actuellement detenu")

    args = parser.parse_args()

    if args.commande == "inventaire":
        inventaire()
    elif args.commande == "purge":
        asyncio.run(purger(args.dry_run))
    elif args.commande == "effacer":
        asyncio.run(effacer(args.telephone, args.garage,
                            args.tous_garages, args.dry_run))


if __name__ == "__main__":
    main()
