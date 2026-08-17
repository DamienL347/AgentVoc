"""
Lit la configuration REELLE des assistants Vapi (lecture seule).

Pourquoi : les assistants de test ont ete regles a la main (latence, tokens,
voix) alors que `create_assistant` impose ses propres valeurs codees en dur.
Chaque garage onboarde automatiquement repart donc avec les valeurs du code, pas
avec les reglages eprouves. Ce script sert a recuperer ces reglages pour les
reporter dans le code.

Aucun effet de bord : uniquement des GET. Aucun assistant n'est cree, modifie
ni supprime.

Usage :
    venv\\Scripts\\python.exe scripts/read_vapi_config.py
    venv\\Scripts\\python.exe scripts/read_vapi_config.py --id <assistant_id>
    venv\\Scripts\\python.exe scripts/read_vapi_config.py --json > config.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Le mode simule intercepterait l'appel : ici on veut la VRAIE API Vapi.
os.environ["PROVIDER_MODE"] = "real"

from dotenv import load_dotenv   # noqa: E402
load_dotenv()

import httpx   # noqa: E402

BASE_URL = os.getenv("VAPI_API_BASE_URL", "https://api.vapi.ai")
CLE      = os.getenv("VAPI_PRIVATE_KEY", "")

# Champs a ne jamais afficher : une cle recopiee dans un terminal finit dans un
# historique, un screenshot ou un copier-coller.
# Noms EXACTS (en minuscules) : un filtre par sous-chaine masquait « maxTokens »
# a cause de « token », alors que c'est un reglage a reporter, pas un secret.
SENSIBLES = {
    "apikey", "token", "secret", "password", "credential", "credentials",
    "authorization", "twilioauthtoken", "privatekey", "publickey",
    "accountsid", "authtoken",
}


def masquer(valeur, cle: str = ""):
    """Masque recursivement les champs dont le NOM est exactement sensible."""
    if cle.lower() in SENSIBLES:
        return "***masque***"
    if isinstance(valeur, dict):
        return {k: masquer(v, k) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [masquer(v, cle) for v in valeur]
    return valeur


def lister() -> list[dict]:
    reponse = httpx.get(
        f"{BASE_URL}/assistant",
        headers={"Authorization": f"Bearer {CLE}"},
        timeout=30.0,
    )
    reponse.raise_for_status()
    donnees = reponse.json()
    return donnees if isinstance(donnees, list) else [donnees]


def afficher(a: dict) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {a.get('name', '(sans nom)')}")
    print(f"  id : {a.get('id')}")
    print(f"{'=' * 72}")

    modele = a.get("model") or {}
    voix   = a.get("voice") or {}
    stt    = a.get("transcriber") or {}

    print("\nLLM")
    for champ in ("provider", "model", "temperature", "maxTokens",
                  "emotionRecognitionEnabled", "numFastTurns"):
        if champ in modele:
            print(f"  {champ:28} {modele[champ]}")
    outils = modele.get("toolIds") or modele.get("tools") or []
    print(f"  {'outils attaches':28} {len(outils)}")

    print("\nVOIX (TTS)")
    for champ, valeur in voix.items():
        if champ in ("provider", "voiceId", "model", "language", "speed",
                     "stability", "similarityBoost", "style", "chunkPlan",
                     "fillerInjectionEnabled", "optimizeStreamingLatency",
                     "useSpeakerBoost", "emotion"):
            print(f"  {champ:28} {valeur}")

    print("\nTRANSCRIPTION (STT)")
    for champ, valeur in stt.items():
        print(f"  {champ:28} {valeur}")

    print("\nCOMPORTEMENT D'APPEL")
    for champ in ("firstMessageMode", "silenceTimeoutSeconds",
                  "maxDurationSeconds", "responseDelaySeconds",
                  "llmRequestDelaySeconds", "numWordsToInterruptAssistant",
                  "backgroundDenoisingEnabled", "backgroundSound",
                  "recordingEnabled", "endCallFunctionEnabled",
                  "dialKeypadFunctionEnabled", "hipaaEnabled",
                  "startSpeakingPlan", "stopSpeakingPlan"):
        if champ in a:
            print(f"  {champ:28} {a[champ]}")

    if a.get("firstMessage"):
        print(f"\nPREMIER MESSAGE\n  \"{a['firstMessage']}\"")

    if a.get("endCallPhrases"):
        print(f"\nPHRASES DE FIN\n  {a['endCallPhrases']}")

    meta = a.get("metadata") or {}
    print(f"\nMETADONNEES\n  {meta}")
    if not meta.get("garage_id"):
        print("  ATTENTION : pas de garage_id — le backend ne pourra pas")
        print("              identifier le tenant sur cet assistant.")

    prompt = ""
    for message in (modele.get("messages") or []):
        if message.get("role") == "system":
            prompt = message.get("content", "")
    if prompt:
        print(f"\nPROMPT SYSTEME : {len(prompt)} caracteres "
              f"(~{round(len(prompt) / 3.6)} tokens estimes)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lecture de la config Vapi")
    parser.add_argument("--id", default=None, help="un assistant en particulier")
    parser.add_argument("--json", action="store_true",
                        help="sortie JSON complete (secrets masques)")
    args = parser.parse_args()

    if not CLE:
        sys.exit("[ERREUR] VAPI_PRIVATE_KEY absente de .env")

    try:
        assistants = lister()
    except httpx.HTTPStatusError as e:
        sys.exit(f"[ERREUR] Vapi a repondu {e.response.status_code} : {e.response.text[:200]}")
    except Exception as e:
        sys.exit(f"[ERREUR] Appel Vapi impossible : {e}")

    if args.id:
        assistants = [a for a in assistants if a.get("id") == args.id]
        if not assistants:
            sys.exit(f"[ERREUR] Assistant {args.id} introuvable")

    if args.json:
        print(json.dumps(masquer(assistants), indent=2, ensure_ascii=False))
        return

    print(f"\n{len(assistants)} assistant(s) trouve(s) chez Vapi")
    for a in assistants:
        afficher(masquer(a))
    print()


if __name__ == "__main__":
    main()
