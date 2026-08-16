"""
Simulateur d'appel — deroule un parcours client complet et affiche ce que
l'agent repondrait, sans telephone, sans Vapi et sans consommer de credits.

Usage :
    venv\\Scripts\\python.exe scripts/simulate_call.py                 # scenario rdv
    venv\\Scripts\\python.exe scripts/simulate_call.py --scenario urgence
    venv\\Scripts\\python.exe scripts/simulate_call.py --list
    venv\\Scripts\\python.exe scripts/simulate_call.py --sans-agenda   # garage non rattache

Necessite PROVIDER_MODE=fake dans .env (defaut). Un garage jetable est cree
puis supprime : aucune donnee reelle n'est touchee.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PROVIDER_MODE", "fake")

# Le simulateur parle a l'utilisateur : les logs applicatifs sont du bruit ici.
import logging                                   # noqa: E402
logging.disable(logging.INFO)

from tests.simulator import CallSimulator        # noqa: E402

CLIENT = "+33612345678"


# ── Affichage ────────────────────────────────────────────────────────────────

def titre(texte: str) -> None:
    print(f"\n{'=' * 72}\n  {texte}\n{'=' * 72}")


def client_dit(texte: str) -> None:
    print(f"\n  CLIENT  > {texte}")


def agent_dit(texte: str) -> None:
    print(f"  AGENT   < {texte}")


def technique(texte: str) -> None:
    print(f"            [{texte}]")


# ── Scenarios ────────────────────────────────────────────────────────────────

def scenario_rdv(sim) -> None:
    call = sim.new_call(caller=CLIENT)
    call.start()
    technique(f"appel entrant de {CLIENT}")

    client_dit("Bonjour, je voudrais faire la revision de ma Clio.")
    dispo = call.tool("check_availability", service_type="revision",
                      preferred_slot="matin")
    agent_dit(dispo.message)

    slots = dispo.body.get("slots", [])
    if not slots:
        technique("aucun creneau — fin du scenario")
        return
    if any(s.get("is_fallback") for s in slots):
        technique("ATTENTION : creneaux de repli — ils n'existent dans AUCUN agenda")

    client_dit(f"Le premier me va : {slots[0]['formatted_fr']}.")
    rdv = call.tool("create_appointment", scheduled_at=slots[0]["start"],
                    client_name="Pierre Moreau", client_phone=CLIENT,
                    service_type="revision", vehicle_brand="Renault",
                    vehicle_model="Clio")
    agent_dit(rdv.message)
    technique(f"calcom_uid = {rdv.body.get('calcom_uid') or 'VIDE (absent de l agenda)'}")

    appts = call.db_appointments()
    if appts:
        conf = call.tool("send_confirmation", client_phone=CLIENT,
                         appointment_id=appts[0]["id"])
        technique(f"confirmation : {conf.message}")

    client_dit("Merci, au revoir !")
    call.end(reason="assistant-ended-call", duration=88,
             summary="RDV revision pris pour une Clio")
    _bilan(call)


def scenario_urgence(sim) -> None:
    call = sim.new_call(caller="+33655443322")
    call.start()
    client_dit("Ma voiture est en panne sur l'A61, je suis bloque !")

    alerte = call.tool("send_sms_alert", priority="critique",
                       message="Panne A61, vehicule immobilise, client bloque")
    agent_dit(alerte.message)

    transfert = call.tool("transfer_call", reason="urgence",
                          summary="Panne autoroute, depannage immediat")
    agent_dit(transfert.message)
    technique(f"transfert vers {transfert.body.get('transfer_phone')}")

    call.end(reason="assistant-ended-call", duration=52,
             summary="Urgence depannage A61")
    _bilan(call)


def scenario_annulation(sim) -> None:
    call = sim.new_call(caller=CLIENT)
    call.start()

    client_dit("Bonjour, je voudrais une vidange.")
    dispo = call.tool("check_availability", service_type="vidange")
    agent_dit(dispo.message)

    slots = dispo.body.get("slots", [])
    rdv = call.tool("create_appointment", scheduled_at=slots[0]["start"],
                    client_name="Marie Dupont", client_phone=CLIENT,
                    service_type="vidange")
    agent_dit(rdv.message)

    client_dit("Finalement j'ai un imprevu, je dois annuler.")
    retrouve = call.tool("get_appointment_by_phone", client_phone=CLIENT)
    agent_dit(retrouve.message)

    annule = call.tool("cancel_appointment",
                       appointment_id=rdv.body["appointment_id"],
                       reason="Imprevu client")
    agent_dit(annule.message)

    call.end(duration=76, summary="RDV vidange pris puis annule")
    _bilan(call)


def scenario_mecontentement(sim) -> None:
    call = sim.new_call(caller=CLIENT)
    call.start()

    client_dit("C'est inadmissible, ma voiture est ressortie avec le meme probleme !")
    transfert = call.tool("transfer_call", reason="reclamation",
                          summary="Client mecontent, probleme non resolu")
    agent_dit(transfert.message)

    call.end(duration=45, summary="Reclamation transferee au patron")
    _bilan(call)


def scenario_message(sim) -> None:
    call = sim.new_call(caller=CLIENT)
    call.start()

    client_dit("Je voudrais un devis pour un embrayage sur ma Golf de 2015.")
    msg = call.tool("take_message", client_name="Paul Durand", client_phone=CLIENT,
                    message="Devis embrayage Golf 2015")
    agent_dit(msg.message)

    call.end(duration=38, summary="Demande de devis embrayage")
    _bilan(call)


def scenario_voiture_prete(sim) -> None:
    call = sim.new_call(caller=CLIENT)
    call.start()

    client_dit("Bonjour, je voulais savoir si ma voiture est prete ?")
    res = call.tool("check_vehicle_status", client_phone=CLIENT)
    agent_dit(res.message)
    technique(f"decision de l'outil : {res.body.get('action')}")

    if res.body.get("action") == "take_message":
        client_dit("Oui, Pierre Moreau, au 06 12 34 56 78.")
        msg = call.tool("take_message", client_name="Pierre Moreau",
                        client_phone=CLIENT, message="Souhaite savoir si sa Clio est prete")
        agent_dit(msg.message)

    call.end(duration=41, summary="Demande d'etat du vehicule")
    _bilan(call)


def scenario_creneau_pris(sim) -> None:
    call = sim.new_call(caller=CLIENT)
    call.start()

    client_dit("Je voudrais un rendez-vous pour une revision.")
    dispo = call.tool("check_availability", service_type="revision")
    agent_dit(dispo.message)

    creneau = dispo.body["slots"][0]["start"]
    call.tool("create_appointment", scheduled_at=creneau, client_name="Pierre Moreau",
              client_phone=CLIENT, service_type="revision")
    technique("pendant ce temps, un autre client reserve le meme creneau...")

    autre = sim.new_call(caller="+33622334455")
    autre.start()
    client_dit("(2e client) Je prends le meme creneau.")
    conflit = autre.tool("create_appointment", scheduled_at=creneau,
                         client_name="Marie Dupont", client_phone="+33622334455",
                         service_type="revision")
    agent_dit(conflit.message)
    technique(f"conflit detecte = {conflit.body.get('conflict')}")

    autre.end(duration=55, summary="Creneau indisponible, a rappeler")
    _bilan(autre)


SCENARIOS = {
    "rdv":            ("Prise de rendez-vous complete",        scenario_rdv),
    "annulation":     ("Prise puis annulation de RDV",         scenario_annulation),
    "urgence":        ("Urgence depannage + transfert",        scenario_urgence),
    "mecontentement": ("Client mecontent -> transfert humain", scenario_mecontentement),
    "message":        ("Demande de devis -> message au patron", scenario_message),
    "voiture-prete":  ("« Ma voiture est-elle prete ? »",      scenario_voiture_prete),
    "creneau-pris":   ("Creneau reserve pendant l'appel",      scenario_creneau_pris),
}


def _bilan(call) -> None:
    """Ce qui a REELLEMENT ete enregistre, au-dela de ce que l'agent a dit."""
    enregistre = call.db_call() or {}
    print(f"\n  --- Bilan ---")
    print(f"  Appel      : statut={enregistre.get('call_status')} "
          f"duree={enregistre.get('duration_seconds')}s")
    print(f"  RDV        : {len(call.db_appointments())}")
    print(f"  SMS        : {len(call.sms_sent())}  (simules)")
    print(f"  Emails     : {len(call.emails_sent())}  (simules)")
    print(f"  Notifs BDD : {len(call.db_notifications())}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulateur d'appel AgentLumy")
    parser.add_argument("--scenario", default="rdv", choices=list(SCENARIOS))
    parser.add_argument("--list", action="store_true", help="liste les scenarios")
    parser.add_argument("--sans-agenda", action="store_true",
                        help="garage dont l'agenda Cal.com n'est pas rattache")
    parser.add_argument("--ferme", action="store_true",
                        help="garage ferme : transfert impossible, prise de message")
    args = parser.parse_args()

    if args.list:
        print("\nScenarios disponibles :\n")
        for cle, (libelle, _) in SCENARIOS.items():
            print(f"  {cle:16} {libelle}")
        return

    libelle, fonction = SCENARIOS[args.scenario]
    titre(f"{libelle}"
          + ("  (SANS agenda rattache)" if args.sans_agenda else "")
          + ("  (garage FERME)" if args.ferme else ""))

    with CallSimulator(calcom_ready=not args.sans_agenda,
                       ouvert=not args.ferme) as sim:
        technique(f"garage jetable {sim.garage_id}")
        fonction(sim)

    print("\n  Garage de test supprime. Aucun SMS, aucun appel, aucun euro depense.\n")


if __name__ == "__main__":
    main()
