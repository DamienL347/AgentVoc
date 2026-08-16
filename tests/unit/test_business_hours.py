"""
Tests des horaires d'ouverture.

Enjeu : ces fonctions décident si l'agent transfère l'appel ou prend un message.
Se tromper, c'est envoyer un client — souvent mécontent ou en panne — vers un
téléphone qui sonne dans le vide.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.utils.business_hours import (
    describe_hours_fr,
    is_open_at,
    next_opening_fr,
)

PARIS = ZoneInfo("Europe/Paris")

HORAIRES = {
    "monday":    {"open": "08:00", "close": "18:00", "closed": False},
    "tuesday":   {"open": "08:00", "close": "18:00", "closed": False},
    "wednesday": {"open": "08:00", "close": "18:00", "closed": False},
    "thursday":  {"open": "08:00", "close": "18:00", "closed": False},
    "friday":    {"open": "08:00", "close": "18:00", "closed": False},
    "saturday":  {"open": "08:00", "close": "12:00", "closed": False},
    "sunday":    {"open": None,    "close": None,    "closed": True},
}

# Repères : 17/08/2026 est un lundi, 22/08 un samedi, 23/08 un dimanche
LUNDI_10H    = datetime(2026, 8, 17, 10, 0, tzinfo=PARIS)
LUNDI_7H     = datetime(2026, 8, 17,  7, 0, tzinfo=PARIS)
LUNDI_18H    = datetime(2026, 8, 17, 18, 0, tzinfo=PARIS)
SAMEDI_11H   = datetime(2026, 8, 22, 11, 0, tzinfo=PARIS)
SAMEDI_15H   = datetime(2026, 8, 22, 15, 0, tzinfo=PARIS)
DIMANCHE_10H = datetime(2026, 8, 23, 10, 0, tzinfo=PARIS)


def test_ouvert_en_pleine_journee():
    assert is_open_at(HORAIRES, LUNDI_10H) is True


def test_ferme_avant_ouverture():
    assert is_open_at(HORAIRES, LUNDI_7H) is False


def test_ferme_a_l_heure_pile_de_fermeture():
    """18h00 pile : le garage ferme, on ne transfère plus."""
    assert is_open_at(HORAIRES, LUNDI_18H) is False


def test_samedi_matin_ouvert_apres_midi_ferme():
    assert is_open_at(HORAIRES, SAMEDI_11H) is True
    assert is_open_at(HORAIRES, SAMEDI_15H) is False


def test_dimanche_ferme():
    assert is_open_at(HORAIRES, DIMANCHE_10H) is False


def test_horaires_absents_ou_invalides_ferme():
    """Sans horaires exploitables, on préfère prendre un message à tort."""
    assert is_open_at(None, LUNDI_10H) is False
    assert is_open_at({}, LUNDI_10H) is False
    assert is_open_at({"monday": "n'importe quoi"}, LUNDI_10H) is False
    assert is_open_at({"monday": {"open": "8h", "close": "18h"}}, LUNDI_10H) is False


# ── Prochaine ouverture ──────────────────────────────────────────────────────

def test_prochaine_ouverture_le_lendemain():
    assert next_opening_fr(HORAIRES, LUNDI_18H) == "demain à 8h"


def test_prochaine_ouverture_saute_le_dimanche():
    """Samedi après-midi : la prochaine ouverture est lundi, pas dimanche."""
    assert next_opening_fr(HORAIRES, SAMEDI_15H) == "lundi à 8h"


def test_prochaine_ouverture_le_jour_meme():
    assert next_opening_fr(HORAIRES, LUNDI_7H) == "aujourd'hui à 8h"


# ── Description ──────────────────────────────────────────────────────────────

def test_description_omet_les_jours_fermes():
    texte = describe_hours_fr(HORAIRES)
    assert "lundi 08:00-18:00" in texte
    assert "samedi 08:00-12:00" in texte
    assert "dimanche" not in texte


def test_description_sans_horaires():
    assert "pas renseigné" in describe_hours_fr(None)
