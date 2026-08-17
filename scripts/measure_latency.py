"""
Mesure la latence des outils appeles par l'agent vocal.

Pourquoi ca compte : pendant qu'un outil repond, l'agent est MUET au telephone.
Le budget total d'un tour de parole (~800 ms) se partage entre STT, LLM, TTS et
notre backend. Chaque milliseconde ici est prise sur les autres.

Ce que la mesure couvre : notre code + les allers-retours vers Supabase (reel).
Ce qu'elle ne couvre pas : le reseau vers Cal.com / Twilio (simule en fake), ni
STT/LLM/TTS qui vivent chez Vapi. Le chiffre est donc un PLANCHER — en
production, ajouter la latence Cal.com sur les outils qui l'appellent.

Le nombre de requetes Supabase est affiche a cote du temps : c'est le vrai
levier. Chaque requete est un aller-retour reseau (~50-150 ms depuis un poste
de dev, moins depuis Cloud Run en europe-west1).

Usage :
    venv\\Scripts\\python.exe scripts/measure_latency.py
    venv\\Scripts\\python.exe scripts/measure_latency.py --iterations 10
"""
import argparse
import logging
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PROVIDER_MODE", "fake")

from dotenv import load_dotenv   # noqa: E402
load_dotenv()

from tests.simulator import CallSimulator   # noqa: E402

CLIENT = "+33612345678"

# Budget indicatif : au-dela, l'agent marque un silence perceptible
SEUIL_VERT  = 150   # ms
SEUIL_ORANGE = 400  # ms


class CompteurRequetes(logging.Handler):
    """
    Compte les requetes HTTP sortantes.

    httpx journalise chaque requete en INFO : on s'y branche plutot que
    d'instrumenter le client Supabase, dont l'API interne peut changer.
    """

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.supabase = 0
        self.autres   = 0
        self.actif    = False

    def emit(self, record):
        if not self.actif:
            return
        message = record.getMessage()
        if "HTTP Request" not in message:
            return
        if "supabase.co" in message:
            self.supabase += 1
        elif "testserver" not in message:
            self.autres += 1

    def reset(self):
        self.supabase = 0
        self.autres   = 0


def couleur(ms: float) -> str:
    if ms < SEUIL_VERT:
        return "ok"
    if ms < SEUIL_ORANGE:
        return "moyen"
    return "LENT"


def mesurer(call, compteur, tool: str, iterations: int, **params) -> dict:
    """Chronometre un outil sur N iterations. Retourne mediane, p95, requetes."""
    durees = []
    requetes = None

    for i in range(iterations):
        compteur.reset()
        compteur.actif = True
        depart = time.perf_counter()

        call.tool(tool, **params)

        ecoule = (time.perf_counter() - depart) * 1000
        compteur.actif = False

        # La 1re iteration paie les imports tardifs et l'etablissement des
        # connexions : on la garde a part pour ne pas fausser la mediane.
        if i == 0:
            premiere = ecoule
            requetes = compteur.supabase
        else:
            durees.append(ecoule)

    if not durees:
        durees = [premiere]

    return {
        "tool":     tool,
        "premiere": premiere,
        "mediane":  statistics.median(durees),
        "max":      max(durees),
        "requetes": requetes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mesure de latence des outils")
    parser.add_argument("--iterations", type=int, default=6)
    args = parser.parse_args()

    # On coupe le bruit applicatif mais on garde httpx pour compter les requetes
    logging.getLogger("app").setLevel(logging.ERROR)
    compteur = CompteurRequetes()
    logging.getLogger("httpx").addHandler(compteur)
    logging.getLogger("httpx").setLevel(logging.INFO)

    print(f"\nMesure sur {args.iterations} iterations par outil")
    print("(providers simules, Supabase reel — le chiffre est un plancher)\n")

    resultats = []

    with CallSimulator() as sim:
        call = sim.new_call(caller=CLIENT)
        call.start()

        # Un RDV existant, necessaire aux outils de consultation/annulation
        dispo = call.tool("check_availability", service_type="revision")
        creneau = dispo.body["slots"][0]["start"]
        rdv = call.tool("create_appointment", scheduled_at=creneau,
                        client_name="Pierre Moreau", client_phone=CLIENT,
                        service_type="revision")
        appointment_id = rdv.body.get("appointment_id")

        resultats.append(mesurer(call, compteur, "check_availability",
                                 args.iterations, service_type="revision"))
        resultats.append(mesurer(call, compteur, "get_appointment_by_phone",
                                 args.iterations, client_phone=CLIENT))
        resultats.append(mesurer(call, compteur, "check_vehicle_status",
                                 args.iterations, client_phone=CLIENT))
        resultats.append(mesurer(call, compteur, "take_message",
                                 args.iterations, client_name="Pierre",
                                 client_phone=CLIENT, message="Test latence"))
        resultats.append(mesurer(call, compteur, "transfer_call",
                                 args.iterations, reason="demande_client",
                                 summary="Test latence"))
        resultats.append(mesurer(call, compteur, "send_sms_alert",
                                 args.iterations, priority="normale",
                                 message="Test latence"))
        if appointment_id:
            resultats.append(mesurer(call, compteur, "send_confirmation",
                                     args.iterations, client_phone=CLIENT,
                                     appointment_id=appointment_id))

    # ── Rapport ──────────────────────────────────────────────────────────────
    print(f"{'Outil':28} {'mediane':>9} {'max':>9} {'1er appel':>10} "
          f"{'req. BDD':>9}  etat")
    print("-" * 78)

    for r in sorted(resultats, key=lambda x: -x["mediane"]):
        print(f"{r['tool']:28} {r['mediane']:>7.0f}ms {r['max']:>7.0f}ms "
              f"{r['premiere']:>8.0f}ms {r['requetes']:>9}  {couleur(r['mediane'])}")

    medianes = [r["mediane"] for r in resultats]
    total_req = sum(r["requetes"] or 0 for r in resultats)

    print("-" * 78)
    print(f"{'MEDIANE GLOBALE':28} {statistics.median(medianes):>7.0f}ms")
    print(f"{'PIRE OUTIL':28} {max(medianes):>7.0f}ms")
    print(f"{'requetes BDD cumulees':28} {total_req:>9}")

    lents = [r for r in resultats if r["mediane"] >= SEUIL_ORANGE]
    if lents:
        print(f"\n{len(lents)} outil(s) au-dela de {SEUIL_ORANGE} ms — "
              f"silence perceptible au telephone :")
        for r in lents:
            print(f"   • {r['tool']} ({r['mediane']:.0f}ms, "
                  f"{r['requetes']} requetes BDD)")
    print()


if __name__ == "__main__":
    main()
