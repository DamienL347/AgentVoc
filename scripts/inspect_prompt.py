"""
Audite le prompt systeme genere pour un garage.

Pourquoi : le prompt est la seule chose qui pilote le LLM en appel reel. Un
placeholder oublie, un outil cite qui n'existe pas, ou un outil existant jamais
documente — et l'agent improvise au telephone devant un client. Rien dans le
code ne signale ces incoherences : elles ne se voient qu'a l'usage.

Ce script verifie, sans consommer un seul token :
  • variables {{...}} non remplacees
  • outils cites dans le prompt mais NON declares cote Vapi (l'agent
    appellerait une fonction inexistante)
  • outils declares mais JAMAIS mentionnes dans le prompt (l'agent ignore
    qu'il les a)
  • poids du prompt : il est renvoye au LLM a CHAQUE tour de parole, donc il
    pese sur la latence et sur le cout de chaque appel

Usage :
    venv\\Scripts\\python.exe scripts/inspect_prompt.py
    venv\\Scripts\\python.exe scripts/inspect_prompt.py --type depanneur_remorquage
    venv\\Scripts\\python.exe scripts/inspect_prompt.py --afficher
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PROVIDER_MODE", "fake")

from dotenv import load_dotenv   # noqa: E402
load_dotenv()

from app.prompts.system_prompt import (          # noqa: E402
    GarageType,
    PromptGenerator,
)

# Garage de reference : toutes les donnees renseignees, pour qu'un placeholder
# vide signale un vrai defaut du modele et non une donnee manquante.
GARAGE_TEST = {
    "name":         "Garage Martin",
    "agent_name":   "Lea",
    "garage_type":  "mecanique_generale",
    "address_street": "12 rue de la Mecanique",
    "address_city": "Toulouse",
    "phone_number": "+33561000001",
    "email":        "contact@garage-martin.fr",
    "transfer_phone_number": "+33600000001",
    "business_hours": {
        "monday":    {"open": "08:00", "close": "18:00", "closed": False},
        "tuesday":   {"open": "08:00", "close": "18:00", "closed": False},
        "wednesday": {"open": "08:00", "close": "18:00", "closed": False},
        "thursday":  {"open": "08:00", "close": "18:00", "closed": False},
        "friday":    {"open": "08:00", "close": "18:00", "closed": False},
        "saturday":  {"open": "08:00", "close": "12:00", "closed": False},
        "sunday":    {"open": None, "close": None, "closed": True},
    },
}

SERVICES_TEST = [
    {"name": "Revision complete", "duration_minutes": 90},
    {"name": "Vidange",           "duration_minutes": 45},
    {"name": "Freins",            "duration_minutes": 60},
]


def outils_declares() -> set[str]:
    """Noms des outils reellement declares a Vapi."""
    from app.integrations.vapi_client import vapi_client

    definitions = vapi_client._build_tools_config()
    return {
        d["function"]["name"]
        for d in definitions
        if isinstance(d, dict) and "function" in d
    }


def outils_cites(prompt: str, connus: set[str]) -> set[str]:
    """
    Outils mentionnes dans le prompt.

    On cherche `nom(` et `nom()` : c'est ainsi que le modele les presente. On
    restreint aux identifiants plausibles pour ne pas ramasser des tournures
    francaises suivies d'une parenthese.
    """
    candidats = set(re.findall(r"\b([a-z_][a-z0-9_]{3,})\s*\(", prompt))
    # Un outil inconnu n'est signale que s'il ressemble a un appel d'outil
    return {c for c in candidats if c in connus or "_" in c}


def estimer_tokens(texte: str) -> int:
    """
    Estimation grossiere : ~3,6 caracteres par token en francais.
    Suffisant pour un ordre de grandeur ; le compte exact demanderait le
    tokenizer du modele.
    """
    return round(len(texte) / 3.6)


def auditer(garage_type: str, afficher: bool) -> int:
    """Retourne le nombre de problemes bloquants trouves."""
    generateur = PromptGenerator()
    garage = {**GARAGE_TEST, "garage_type": garage_type}

    prompt  = generateur.generate(garage_data=garage, services=SERVICES_TEST)
    premier = generateur.generate_first_message(garage)

    print(f"\n{'=' * 72}")
    print(f"  AUDIT DU PROMPT — {garage_type}")
    print(f"{'=' * 72}")

    problemes = 0

    # ── Poids ────────────────────────────────────────────────────────────────
    tokens = estimer_tokens(prompt)
    print(f"\nPoids")
    print(f"  caracteres      : {len(prompt):,}")
    print(f"  lignes          : {len(prompt.splitlines())}")
    print(f"  tokens estimes  : ~{tokens:,}")
    print(f"  -> renvoye au LLM a CHAQUE tour de parole")
    if tokens > 2000:
        print(f"  ATTENTION : au-dela de ~2000 tokens, chaque tour paie ce poids")
        print(f"              en latence et en cout. Envisager de condenser.")

    # ── Placeholders non remplaces ───────────────────────────────────────────
    restants = re.findall(r"\{\{([A-Z_]+)\}\}", prompt)
    print(f"\nVariables non remplacees : {len(set(restants))}")
    if restants:
        problemes += len(set(restants))
        for v in sorted(set(restants)):
            print(f"  MANQUANT {{{{{v}}}}} — l'agent lira ce texte brut a voix haute")
    else:
        print("  aucune (toutes les donnees du garage ont ete injectees)")

    # ── Coherence des outils ─────────────────────────────────────────────────
    declares = outils_declares()
    cites    = outils_cites(prompt, declares)

    fantomes = cites - declares          # cites mais inexistants
    muets    = declares - cites          # existants mais non documentes

    print(f"\nOutils declares a Vapi   : {len(declares)}")
    print(f"Outils cites dans le prompt : {len(cites & declares)}")

    if fantomes:
        problemes += len(fantomes)
        print(f"\n  OUTILS FANTOMES ({len(fantomes)}) — cites mais NON declares :")
        for f in sorted(fantomes):
            print(f"    {f}()  <- l'agent tentera un appel qui n'existe pas")

    if muets:
        print(f"\n  OUTILS NON DOCUMENTES ({len(muets)}) — declares mais absents du prompt :")
        for m in sorted(muets):
            print(f"    {m}()  <- l'agent ignore qu'il dispose de cet outil")

    if not fantomes and not muets:
        print("  coherence parfaite entre le prompt et les outils declares")

    # ── Premier message ──────────────────────────────────────────────────────
    print(f"\nPremier message ({len(premier)} caracteres)")
    print(f'  "{premier}"')
    if re.search(r"\{\{", premier):
        problemes += 1
        print("  PROBLEME : variable non remplacee dans la phrase d'accueil")

    if afficher:
        print(f"\n{'=' * 72}\n{prompt}\n{'=' * 72}")

    print(f"\n{'-' * 72}")
    print(f"  {problemes} probleme(s) bloquant(s)" if problemes
          else "  Aucun probleme bloquant")
    print()
    return problemes


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit du prompt systeme")
    parser.add_argument("--type", default=None,
                        choices=[t.value for t in GarageType],
                        help="type de garage (defaut : tous)")
    parser.add_argument("--afficher", action="store_true",
                        help="afficher le prompt complet")
    args = parser.parse_args()

    types = [args.type] if args.type else [t.value for t in GarageType]
    total = sum(auditer(t, args.afficher) for t in types)

    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
