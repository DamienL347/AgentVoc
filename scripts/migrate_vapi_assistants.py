"""
Met a jour les assistants Vapi existants avec les reglages du code.

Pourquoi : le correctif qui attache les outils (ensure_tools + model.toolIds) ne
s'applique qu'aux assistants CREES apres. Les assistants deja en place chez Vapi
gardent leur configuration — et notamment 0 outil, donc un agent qui parle mais
ne peut ni consulter l'agenda, ni prendre un RDV, ni transferer.

Ce script comble l'ecart sans recreer les assistants (ce qui changerait leurs
identifiants, deja references dans Supabase et sur les numeros de telephone).

PRUDENCE — deux garde-fous :

1. **--dry-run par defaut.** Rien n'est modifie tant que --apply n'est pas passe.

2. **Le prompt systeme est preserve.** Vapi remplace l'objet `model` en entier :
   envoyer {"toolIds": [...]} seul effacerait `messages`, donc le prompt de
   l'assistant. Le script relit la config existante et ne modifie que les champs
   voulus.

Par defaut, seuls les assistants portant un `metadata.garage_id` sont traites :
ce sont ceux issus de l'onboarding. Les assistants regles a la main (comme
« Lumy », qui sert de reference) ne sont pas touches sans --inclure-manuels.

Usage :
    venv\\Scripts\\python.exe scripts/migrate_vapi_assistants.py
    venv\\Scripts\\python.exe scripts/migrate_vapi_assistants.py --apply
    venv\\Scripts\\python.exe scripts/migrate_vapi_assistants.py --id <assistant_id> --apply
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# On vise la VRAIE API : le mode simule intercepterait les appels.
os.environ["PROVIDER_MODE"] = "real"

from dotenv import load_dotenv   # noqa: E402
load_dotenv()

import httpx   # noqa: E402

from app.config import settings                       # noqa: E402
from app.integrations.vapi_client import vapi_client   # noqa: E402

BASE_URL = os.getenv("VAPI_API_BASE_URL", "https://api.vapi.ai")
CLE      = os.getenv("VAPI_PRIVATE_KEY", "")
ENTETES  = {"Authorization": f"Bearer {CLE}", "Content-Type": "application/json"}

MESSAGE_FIN       = "Merci de votre appel, bonne journée !"
MESSAGE_REPONDEUR = ("Bonjour, vous êtes sur le répondeur. "
                     "Rappelez-nous quand vous serez disponible.")
PHRASES_FIN = ["au revoir", "bonne journée", "bonne soirée",
               "à bientôt", "merci au revoir"]


def lister() -> list[dict]:
    r = httpx.get(f"{BASE_URL}/assistant", headers=ENTETES, timeout=30.0)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else [d]


def calculer_changements(a: dict, tool_ids: list[str]) -> tuple[dict, list[str]]:
    """
    Compare un assistant aux reglages du code.

    Retourne (patch, descriptions). Le patch ne contient que ce qui change ;
    un assistant deja conforme ne genere aucun appel reseau.
    """
    patch: dict = {}
    quoi:  list[str] = []

    modele_actuel = a.get("model") or {}
    modele_patch  = {}

    # Outils — la raison d'etre de cette migration
    actuels = modele_actuel.get("toolIds") or []
    if sorted(actuels) != sorted(tool_ids):
        modele_patch["toolIds"] = tool_ids
        quoi.append(f"outils : {len(actuels)} -> {len(tool_ids)}")

    if modele_actuel.get("temperature") != settings.VAPI_TEMPERATURE:
        modele_patch["temperature"] = settings.VAPI_TEMPERATURE
        quoi.append(f"temperature : {modele_actuel.get('temperature')} "
                    f"-> {settings.VAPI_TEMPERATURE}")

    if modele_actuel.get("maxTokens") != settings.VAPI_MAX_TOKENS:
        modele_patch["maxTokens"] = settings.VAPI_MAX_TOKENS
        quoi.append(f"maxTokens : {modele_actuel.get('maxTokens')} "
                    f"-> {settings.VAPI_MAX_TOKENS}")

    if modele_patch:
        # Vapi REMPLACE l'objet model : on renvoie l'existant complet, sinon le
        # prompt systeme (model.messages) serait efface.
        patch["model"] = {**modele_actuel, **modele_patch}

    # Voix
    voix = a.get("voice") or {}
    if settings.CARTESIA_VOICE_ID_FR and voix.get("voiceId") != settings.CARTESIA_VOICE_ID_FR:
        patch["voice"] = {**voix, "voiceId": settings.CARTESIA_VOICE_ID_FR}
        quoi.append(f"voix : {str(voix.get('voiceId'))[:8]}... "
                    f"-> {settings.CARTESIA_VOICE_ID_FR[:8]}...")

    # Repli de transcription : sans lui, une panne Deepgram rend l'agent sourd
    stt = a.get("transcriber") or {}
    if not (stt.get("fallbackPlan") or {}).get("autoFallback", {}).get("enabled"):
        patch["transcriber"] = {**stt, "fallbackPlan": {"autoFallback": {"enabled": True}}}
        quoi.append("repli transcription : activé")

    # Delai de prise de parole (champ actuel)
    if (a.get("startSpeakingPlan") or {}).get("waitSeconds") != settings.VAPI_WAIT_SECONDS:
        patch["startSpeakingPlan"] = {
            **(a.get("startSpeakingPlan") or {}),
            "waitSeconds": settings.VAPI_WAIT_SECONDS,
        }
        quoi.append(f"startSpeakingPlan.waitSeconds : {settings.VAPI_WAIT_SECONDS}")

    # Phrases de fin : des guillemets dans le texte empechent toute correspondance
    phrases = a.get("endCallPhrases") or []
    if any('"' in p for p in phrases) or not phrases:
        patch["endCallPhrases"] = PHRASES_FIN
        if any('"' in p for p in phrases):
            quoi.append("phrases de fin : guillemets parasites retirés")
        else:
            quoi.append("phrases de fin : ajoutées")

    # Messages de fin en francais
    fin = a.get("endCallMessage") or ""
    if not fin or "goodbye" in fin.lower():
        patch["endCallMessage"] = MESSAGE_FIN
        quoi.append(f"message de fin : {fin!r} -> français")

    if not a.get("voicemailMessage"):
        patch["voicemailMessage"] = MESSAGE_REPONDEUR
        quoi.append("message de répondeur : ajouté")

    # Resume d'appel : alimente calls.summary et le dashboard
    analyse = a.get("analysisPlan") or {}
    resume_actuel = (analyse.get("summaryPlan") or {}).get("enabled")
    if resume_actuel != settings.VAPI_ENABLE_SUMMARY:
        patch["analysisPlan"] = {
            **analyse,
            "summaryPlan": {"enabled": settings.VAPI_ENABLE_SUMMARY},
            "successEvaluationPlan": {"enabled": False},
        }
        quoi.append(f"résumé d'appel : {resume_actuel} -> {settings.VAPI_ENABLE_SUMMARY}")

    return patch, quoi


def sauvegarder(assistants: list[dict]) -> Path:
    """
    Sauvegarde la configuration actuelle AVANT toute modification.

    Vapi ne propose pas d'historique : sans cette copie, une modification
    malencontreuse serait irrattrapable. Le fichier contient les prompts
    systeme, donc il reste hors du depot (voir .gitignore).
    """
    import json
    from datetime import datetime

    dossier = Path(__file__).resolve().parent.parent / "backups"
    dossier.mkdir(exist_ok=True)

    chemin = dossier / f"vapi_assistants_{datetime.now():%Y%m%d_%H%M%S}.json"
    chemin.write_text(json.dumps(assistants, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    return chemin


def appliquer(assistant_id: str, patch: dict) -> bool:
    try:
        r = httpx.patch(f"{BASE_URL}/assistant/{assistant_id}",
                        headers=ENTETES, json=patch, timeout=30.0)
        if r.status_code >= 400:
            print(f"      ECHEC {r.status_code} : {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"      ECHEC : {e}")
        return False


async def main_async(args) -> None:
    if not CLE:
        sys.exit("[ERREUR] VAPI_PRIVATE_KEY absente de .env")

    print("\nLecture des assistants Vapi...")
    assistants = lister()

    if args.id:
        assistants = [a for a in assistants if a.get("id") == args.id]
        if not assistants:
            sys.exit(f"[ERREUR] Assistant {args.id} introuvable")
    elif not args.inclure_manuels:
        # Les assistants sans garage_id ont ete crees a la main : on n'y touche
        # pas, ils servent de reference.
        avant = len(assistants)
        assistants = [a for a in assistants
                      if (a.get("metadata") or {}).get("garage_id")]
        ignores = avant - len(assistants)
        if ignores:
            print(f"  {ignores} assistant(s) sans garage_id ignoré(s) "
                  f"(réglés à la main — --inclure-manuels pour les traiter)")

    if not assistants:
        print("  Aucun assistant à traiter.\n")
        return

    print(f"  {len(assistants)} assistant(s) à examiner")

    if args.apply:
        chemin = sauvegarder(assistants)
        print(f"\nSauvegarde avant modification : {chemin.name}")
        print("  (contient les prompts système — non versionné)")

    print("\nOutils disponibles chez Vapi...")
    tool_ids = await vapi_client.ensure_tools() if args.apply else []
    if args.apply:
        if not tool_ids:
            sys.exit("[ERREUR] Aucun outil disponible : migration annulée "
                     "(elle laisserait les assistants sans outil)")
        print(f"  {len(tool_ids)} outil(s) prêts")
    else:
        # En simulation, on ne cree rien : on compte ce qui serait attache.
        tool_ids = [f"(outil {i + 1})"
                    for i in range(len(vapi_client._build_tools_config()))]
        print(f"  {len(tool_ids)} outil(s) seraient attachés "
              f"(aucun n'est créé en simulation)")

    modifies = inchanges = echecs = 0

    print(f"\n{'=' * 72}")
    for a in assistants:
        nom = a.get("name") or "(sans nom)"
        patch, quoi = calculer_changements(a, tool_ids)

        if not patch:
            inchanges += 1
            print(f"\n  {nom}\n      déjà conforme")
            continue

        print(f"\n  {nom}  ({a['id']})")
        for ligne in quoi:
            print(f"      - {ligne}")

        if args.apply:
            if appliquer(a["id"], patch):
                modifies += 1
                print("      -> appliqué")
            else:
                echecs += 1
        else:
            modifies += 1

    print(f"\n{'=' * 72}")
    if args.apply:
        print(f"  {modifies} modifié(s) · {inchanges} déjà conforme(s) · {echecs} échec(s)")
        print("\n  Vérifier le résultat :")
        print("    venv\\Scripts\\python.exe scripts/read_vapi_config.py")
    else:
        print(f"  SIMULATION — {modifies} assistant(s) seraient modifiés, "
              f"{inchanges} déjà conforme(s)")
        print("\n  Rien n'a été modifié. Pour appliquer :")
        print("    venv\\Scripts\\python.exe scripts/migrate_vapi_assistants.py --apply")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aligne les assistants Vapi existants sur les réglages du code")
    parser.add_argument("--apply", action="store_true",
                        help="applique réellement (sinon simulation)")
    parser.add_argument("--id", default=None, help="un assistant en particulier")
    parser.add_argument("--inclure-manuels", action="store_true",
                        help="traiter aussi les assistants sans garage_id")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
