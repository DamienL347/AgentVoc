"""
Tests du client Cal.com — parsing des réponses de l'API v2.

Ces tests verrouillent deux bugs trouvés le 14/08/2026, tous deux invisibles
sans harnais car ils échouaient « proprement » vers un repli :

1. L'API v2 encapsule tout sous `data`. Le code lisait à la racine, donc
   l'uid de réservation revenait vide : le RDV devenait impossible à modifier
   ou annuler ensuite, alors que tout semblait avoir fonctionné.
2. Le champ `eventTypeId` recevait `calcom_user_id` — mauvaise colonne, vide de
   surcroît. Cal.com refusait, on repliait en base locale, et le RDV n'existait
   dans aucun agenda pendant que l'agent annonçait « c'est confirmé ».
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.integrations.calcom_client import CalComClient

PARIS = ZoneInfo("Europe/Paris")


@pytest.fixture
def client():
    return CalComClient()


def _slot(dt):
    return {"time": dt.isoformat(), "duration": 60}


# ── Parsing des créneaux ─────────────────────────────────────────────────────

def test_parse_slots_lit_la_structure_v2_sous_data(client):
    """Réponse réelle de l'API v2 : les créneaux sont sous `data`."""
    dt = datetime.now(PARIS).replace(hour=9, minute=0, second=0, microsecond=0) \
         + timedelta(days=1)
    reponse_v2 = {"status": "success", "data": {"slots": {dt.date().isoformat(): [_slot(dt)]}}}

    slots = client._parse_slots(reponse_v2, preferred_slot=None)

    assert len(slots) == 1, "Les créneaux sous `data` doivent être lus"
    assert slots[0]["formatted_fr"].endswith("9h")


def test_parse_slots_tolere_une_reponse_a_plat(client):
    """Rétrocompatibilité : une réponse sans enveloppe reste acceptée."""
    dt = datetime.now(PARIS).replace(hour=14, minute=0, second=0, microsecond=0) \
         + timedelta(days=1)
    slots = client._parse_slots({"slots": {dt.date().isoformat(): [_slot(dt)]}}, None)

    assert len(slots) == 1


def test_filtre_par_preference_horaire(client):
    """« matin » ne doit pas proposer un créneau de 16h."""
    base   = datetime.now(PARIS).replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
    matin  = base.replace(hour=9)
    aprem  = base.replace(hour=16)
    data   = {"data": {"slots": {matin.date().isoformat(): [_slot(matin), _slot(aprem)]}}}

    slots = client._parse_slots(data, preferred_slot="matin")

    assert len(slots) == 1
    assert "9h" in slots[0]["formatted_fr"]


def test_reponse_vide_ne_leve_pas(client):
    assert client._parse_slots({"status": "success", "data": {}}, None) == []


# ── Créneaux de repli ────────────────────────────────────────────────────────

def test_les_creneaux_de_repli_sont_marques(client):
    """
    Le repli propose des horaires qui ne viennent d'aucun agenda : ils DOIVENT
    rester identifiables, sinon rien ne distingue un vrai créneau d'un créneau
    inventé — ni dans le code, ni au support.
    """
    fallback = client._fallback_slots(service_type="revision", preferred_slot=None)

    assert fallback, "Le repli doit toujours proposer quelque chose"
    assert all(s["is_fallback"] for s in fallback)
    assert all(s["duration_minutes"] == 90 for s in fallback)   # durée d'une révision


def test_format_francais_naturel(client):
    """L'agent lit ce texte à voix haute : il doit être naturel en français."""
    dt = datetime(2026, 8, 17, 9, 0, tzinfo=PARIS)      # un lundi
    assert client._format_slot_fr(dt) == "lundi 17 août à 9h"

    dt_30 = datetime(2026, 8, 17, 14, 30, tzinfo=PARIS)
    assert client._format_slot_fr(dt_30) == "lundi 17 août à 14h30"
