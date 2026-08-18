"""
Apercu du rapport hebdomadaire, sans rien envoyer.

Genere le HTML dans previews/ pour le relire dans un navigateur avant de
l'adresser a un client. Deux modes :

    # donnees d'exemple (aucune connexion requise)
    venv\\Scripts\\python.exe scripts/preview_rapport.py

    # donnees reelles d'un garage
    venv\\Scripts\\python.exe scripts/preview_rapport.py --garage <uuid>

Aucun email n'est envoye : ce script n'appelle jamais Resend.
"""
import argparse
import os
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PROVIDER_MODE", "fake")

from dotenv import load_dotenv   # noqa: E402
load_dotenv()

from app.services.weekly_report import weekly_report   # noqa: E402

SORTIE = Path(__file__).resolve().parent.parent / "previews"

# Semaine plausible d'un garage de quartier : la majorite des appels arrive
# pendant l'ouverture, une minorite non negligeable en dehors — c'est justement
# celle-la que l'agent recupere.
EXEMPLE = {
    "garage_nom":    "Garage Martin",
    "garage_email":  "contact@garage-martin.fr",
    "debut":         datetime.now(timezone.utc) - timedelta(days=7),
    "fin":           datetime.now(timezone.utc),
    "appels_total":  23,
    "hors_horaires": 9,
    "rdv_pris":      11,
    "urgences":      2,
    "messages":      3,
    "transferts":    4,
    "duree_moyenne": 96,
    "demandes": {
        "prise_rdv":            11,
        "information":           5,
        "devis":                 3,
        "depannage_urgent":      2,
        "modification_rdv":      2,
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apercu du rapport hebdomadaire")
    parser.add_argument("--garage", default=None, help="uuid d'un garage reel")
    parser.add_argument("--tel", default="", help="telephone affiche dans la signature")
    parser.add_argument("--pas-d-ouverture", action="store_true",
                        help="ne pas ouvrir le navigateur")
    args = parser.parse_args()

    if args.garage:
        kpis = weekly_report.collecter(args.garage)
        print(f"Donnees reelles — {kpis['garage_nom']} : "
              f"{kpis['appels_total']} appel(s), {kpis['rdv_pris']} RDV")
    else:
        kpis = EXEMPLE
        print("Donnees d'exemple (--garage <uuid> pour des donnees reelles)")

    rendu = weekly_report.rendre(kpis, auteur={"AUTEUR_TEL": args.tel} if args.tel else None)

    SORTIE.mkdir(exist_ok=True)
    fichier = SORTIE / "rapport_hebdomadaire.html"
    fichier.write_text(rendu["html"], encoding="utf-8")
    (SORTIE / "rapport_hebdomadaire.txt").write_text(rendu["texte"], encoding="utf-8")

    print(f"\nSujet : {rendu['sujet']}")
    print(f"HTML  : {fichier}")
    print(f"Texte : {SORTIE / 'rapport_hebdomadaire.txt'}")

    if not args.pas_d_ouverture:
        webbrowser.open(fichier.as_uri())


if __name__ == "__main__":
    main()
