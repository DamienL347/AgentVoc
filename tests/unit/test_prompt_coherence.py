"""
Cohérence des prompts système — garde-fou anti-régression.

Le prompt est la seule chose qui pilote le LLM en appel réel. Trois défauts
possibles, tous invisibles depuis le code :

1. un placeholder `{{VAR}}` oublié → l'agent le lit à voix haute au client ;
2. un outil cité dans le prompt mais non déclaré à Vapi → l'agent tente
   d'appeler une fonction qui n'existe pas (c'était le cas de
   `dispatch_intervention()` chez le dépanneur) ;
3. un outil déclaré mais absent du prompt → l'agent ignore qu'il l'a
   (le dépanneur ne savait pas annuler une intervention).

Ces tests échouent si l'un des trois réapparaît, y compris sur un futur gabarit.
"""
import re

import pytest

from app.integrations.vapi_client import vapi_client
from app.prompts.system_prompt import GarageType, PromptGenerator

# Garage complet : un placeholder vide signale alors un défaut du gabarit,
# pas une donnée manquante.
GARAGE = {
    "name":         "Garage Martin",
    "agent_name":   "Léa",
    "address_street": "12 rue de la Mécanique",
    "address_city": "Toulouse",
    "phone_number": "+33561000001",
    "email":        "contact@garage-martin.fr",
    "transfer_phone_number": "+33600000001",
    "business_hours": {
        j: {"open": "08:00", "close": "18:00", "closed": False}
        for j in ("monday", "tuesday", "wednesday", "thursday", "friday")
    } | {
        "saturday": {"open": "08:00", "close": "12:00", "closed": False},
        "sunday":   {"open": None, "close": None, "closed": True},
    },
}

SERVICES = [
    {"name": "Révision complète", "duration_minutes": 90},
    {"name": "Vidange",           "duration_minutes": 45},
]

TOUS_LES_TYPES = [t.value for t in GarageType]


@pytest.fixture(scope="module")
def outils_declares() -> set[str]:
    return {
        d["function"]["name"]
        for d in vapi_client._build_tools_config()
        if isinstance(d, dict) and "function" in d
    }


def _prompt(garage_type: str) -> str:
    return PromptGenerator().generate(
        garage_data={**GARAGE, "garage_type": garage_type},
        services=SERVICES,
    )


def _outils_cites(prompt: str) -> set[str]:
    """Identifiants de la forme `nom(` — la façon dont le prompt les présente."""
    return {
        c for c in re.findall(r"\b([a-z_][a-z0-9_]{3,})\s*\(", prompt)
        if "_" in c
    }


# ── Placeholders ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("garage_type", TOUS_LES_TYPES)
def test_aucun_placeholder_oublie(garage_type):
    """Un {{VAR}} restant serait lu à voix haute au client."""
    restants = set(re.findall(r"\{\{([A-Z_]+)\}\}", _prompt(garage_type)))
    assert not restants, f"Variables non remplacées dans {garage_type} : {restants}"


@pytest.mark.parametrize("garage_type", TOUS_LES_TYPES)
def test_les_donnees_du_garage_sont_injectees(garage_type):
    """Vérifie que la substitution fonctionne vraiment, pas seulement qu'elle est vide."""
    prompt = _prompt(garage_type)
    assert "Garage Martin" in prompt
    assert "Léa" in prompt


# ── Cohérence avec les outils réellement déclarés ─────────────────────────────

@pytest.mark.parametrize("garage_type", TOUS_LES_TYPES)
def test_aucun_outil_fantome(garage_type, outils_declares):
    """
    Tout outil cité doit exister côté Vapi, sinon l'agent appelle dans le vide.
    """
    fantomes = _outils_cites(_prompt(garage_type)) - outils_declares
    assert not fantomes, (
        f"{garage_type} cite des outils inexistants : {fantomes}. "
        f"Outils déclarés : {sorted(outils_declares)}"
    )


@pytest.mark.parametrize("garage_type", TOUS_LES_TYPES)
def test_tous_les_outils_sont_documentes(garage_type, outils_declares):
    """
    Un outil déclaré mais absent du prompt est un outil que l'agent n'utilisera
    jamais — autant de fonctionnalités payées et inaccessibles.
    """
    manquants = outils_declares - _outils_cites(_prompt(garage_type))
    assert not manquants, (
        f"{garage_type} ne documente pas : {sorted(manquants)}"
    )


# ── Outils côté Vapi ─────────────────────────────────────────────────────────

def test_les_outils_sont_declares_sans_doublon(outils_declares):
    definitions = vapi_client._build_tools_config()
    assert len(definitions) == len(outils_declares), "Deux outils portent le même nom"
    assert len(outils_declares) >= 10


def test_chaque_outil_a_une_url_de_webhook():
    """Sans server.url, Vapi ne sait pas qui appeler."""
    for d in vapi_client._build_tools_config():
        nom = d["function"]["name"]
        url = (d.get("server") or {}).get("url", "")
        assert url, f"{nom} n'a pas de server.url"
        assert url.endswith(f"/{nom}"), (
            f"{nom} pointe vers {url} — l'URL doit correspondre au nom de l'outil, "
            f"sinon l'appel arrive sur le mauvais endpoint"
        )


def test_chaque_outil_a_une_description_utile():
    """
    Le LLM choisit l'outil à partir de sa description : trop vague, il se trompe.
    """
    for d in vapi_client._build_tools_config():
        description = d["function"].get("description", "")
        assert len(description) >= 30, (
            f"{d['function']['name']} : description trop courte pour guider le choix"
        )


# ── Poids du prompt ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("garage_type", TOUS_LES_TYPES)
def test_le_prompt_reste_dans_une_taille_raisonnable(garage_type):
    """
    Le prompt est renvoyé au LLM à CHAQUE tour de parole : il pèse sur la
    latence et sur le coût de chaque appel. Ce plafond est un garde-fou contre
    la dérive, pas une cible.
    """
    caracteres = len(_prompt(garage_type))
    assert caracteres < 20_000, (
        f"{garage_type} : {caracteres} caractères — prompt trop lourd, "
        f"à condenser avant d'ajouter de nouvelles instructions"
    )


# ── Premier message ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("garage_type", TOUS_LES_TYPES)
def test_le_premier_message_annonce_l_enregistrement(garage_type):
    """
    Obligation RGPD : l'appelant doit être informé de l'enregistrement dès le
    décrochage, pas au milieu de la conversation.
    """
    premier = PromptGenerator().generate_first_message(
        {**GARAGE, "garage_type": garage_type}
    )
    assert "{{" not in premier, "Variable non remplacée dans la phrase d'accueil"
    assert "enregistr" in premier.lower(), (
        f"Le premier message n'informe pas de l'enregistrement : {premier!r}"
    )
