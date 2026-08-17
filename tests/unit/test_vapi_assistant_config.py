"""
Configuration des assistants Vapi — garde-fou.

Les réglages de l'agent (température, voix, délai de prise de parole) ont été
éprouvés à la main sur l'assistant « Lumy », mais le code en imposait d'autres :
chaque garage onboardé automatiquement repartait avec des valeurs non testées, et
surtout **une autre voix** que celle retenue.

Ces tests vérifient que les réglages du fichier de configuration arrivent bien
dans le payload envoyé à Vapi, et que les défauts relevés sur l'assistant manuel
ne sont pas réintroduits.
"""
import os

import pytest

os.environ.setdefault("PROVIDER_MODE", "fake")

from uuid import uuid4   # noqa: E402

from app.config import settings                      # noqa: E402
from app.integrations.vapi_client import vapi_client  # noqa: E402


async def _payload() -> dict:
    """
    Assistant créé en mode simulé : le fake renvoie le payload transmis.

    Helper plutôt que fixture : une fixture async exige pytest_asyncio.fixture,
    et ce détour d'outillage n'apporte rien ici.
    """
    return await vapi_client.create_assistant(
        garage_id=uuid4(),
        garage_name="Garage Martin",
        system_prompt="Tu es Léa.",
        first_message="Bonjour !",
    )


# ── Réglages issus de la configuration ────────────────────────────────────────

@pytest.mark.asyncio
async def test_les_reglages_viennent_de_la_configuration():
    """Ni température ni maxTokens ne doivent être codés en dur."""
    payload = await _payload()
    modele = payload["model"]
    assert modele["temperature"] == settings.VAPI_TEMPERATURE
    assert modele["maxTokens"] == settings.VAPI_MAX_TOKENS


@pytest.mark.asyncio
async def test_la_voix_configuree_est_utilisee():
    """
    La voix est un choix produit : celle du fichier de configuration doit être
    appliquée, sans quoi les clients entendent une autre voix que celle retenue.
    """
    payload = await _payload()
    assert payload["voice"]["voiceId"] == settings.CARTESIA_VOICE_ID_FR
    assert payload["voice"]["provider"] == "cartesia"


@pytest.mark.asyncio
async def test_delai_de_prise_de_parole_par_startSpeakingPlan():
    """
    Le réglage passe par startSpeakingPlan. `responseDelaySeconds` est l'ancien
    champ : l'envoyer risquerait de voir le réglage ignoré en silence.
    """
    payload = await _payload()
    assert payload["startSpeakingPlan"]["waitSeconds"] == settings.VAPI_WAIT_SECONDS
    assert "responseDelaySeconds" not in payload


# ── Robustesse ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bascule_automatique_si_la_transcription_tombe():
    """Sans plan de secours, une panne Deepgram rend l'agent sourd."""
    payload = await _payload()
    plan = payload["transcriber"].get("fallbackPlan") or {}
    assert plan.get("autoFallback", {}).get("enabled") is True


@pytest.mark.asyncio
async def test_les_outils_sont_attaches():
    """
    Le bug le plus grave rencontré : un assistant sans outil peut parler mais ne
    peut ni consulter l'agenda, ni prendre un RDV, ni transférer.
    """
    payload = await _payload()
    outils = payload["model"].get("toolIds") or []
    assert len(outils) >= 10, f"Seulement {len(outils)} outil(s) attaché(s)"


@pytest.mark.asyncio
async def test_le_tenant_est_identifiable():
    """garage_id dans les métadonnées : c'est par là que le backend reconnaît le garage."""
    payload = await _payload()
    assert payload["metadata"]["garage_id"]


# ── Défauts relevés sur l'assistant manuel, à ne pas reproduire ──────────────

@pytest.mark.asyncio
async def test_les_phrases_de_fin_sont_sans_guillemets():
    """
    Sur l'assistant réglé à la main, les phrases étaient saisies `"Au revoir"` :
    les guillemets faisaient partie du texte cherché, donc la détection de fin
    d'appel ne pouvait jamais correspondre à ce que dit un client.
    """
    payload = await _payload()
    for phrase in payload["endCallPhrases"]:
        assert '"' not in phrase, f"Guillemet parasite dans {phrase!r}"
        assert phrase == phrase.strip(), f"Espaces superflus dans {phrase!r}"


@pytest.mark.asyncio
async def test_les_messages_de_fin_sont_en_francais():
    """L'assistant manuel avait gardé le « Goodbye. » par défaut de Vapi."""
    payload = await _payload()
    fin = payload.get("endCallMessage", "")
    assert fin, "Aucun message de fin d'appel"
    assert "goodbye" not in fin.lower(), "Message de fin en anglais"

    repondeur = payload.get("voicemailMessage", "")
    assert repondeur, "Aucun message de répondeur"


# ── Arbitrage coût / visibilité ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_le_resume_suit_la_configuration():
    """
    Le résumé Vapi alimente `calls.summary`, affiché au dashboard. Il coûte un
    appel LLM par conversation : le choix doit rester explicite, pas subi.
    """
    payload = await _payload()
    plan = payload["analysisPlan"]["summaryPlan"]
    assert plan["enabled"] == settings.VAPI_ENABLE_SUMMARY


@pytest.mark.asyncio
async def test_evaluation_de_succes_desactivee():
    """Analyse facturée dont rien n'exploite le résultat côté produit."""
    payload = await _payload()
    assert payload["analysisPlan"]["successEvaluationPlan"]["enabled"] is False
