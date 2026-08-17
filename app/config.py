"""
Configuration centralisée de l'application
Toutes les variables d'environnement sont chargées ici
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration de l'application chargée depuis .env
    Validation automatique par Pydantic au démarrage.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    APP_ENV:          str = "development"
    APP_NAME:         str = "voice-agent-garage"
    APP_PORT:         int = 8080
    APP_BASE_URL:     str = "http://localhost:8080"
    APP_FRONTEND_URL:  str = "http://localhost:3000"
    LOG_LEVEL:        str = "INFO"
    SECRET_KEY:       str = "change-me-in-production"

    # ── Localisation ─────────────────────────────────────────
    DEFAULT_TIMEZONE: str = "Europe/Paris"
    DEFAULT_LOCALE:   str = "fr_FR"

    # ── Anthropic ────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL:   str = "claude-haiku-4-5"

    # ── Vapi ─────────────────────────────────────────────────
    VAPI_PUBLIC_KEY:      str = ""
    VAPI_PRIVATE_KEY:     str = ""
    VAPI_WEBHOOK_SECRET:  str = ""
    VAPI_ASSISTANT_ID:    str = ""
    VAPI_API_BASE_URL:    str = "https://api.vapi.ai"

    # ── Deepgram ─────────────────────────────────────────────
    DEEPGRAM_API_KEY: str = ""

    # ── Cartesia ─────────────────────────────────────────────
    CARTESIA_API_KEY:     str = ""
    CARTESIA_VOICE_ID_FR: str = ""
    CARTESIA_MODEL:       str = "sonic-multilingual"

    # ── Twilio ───────────────────────────────────────────────
    TWILIO_ACCOUNT_SID:           str = ""
    TWILIO_AUTH_TOKEN:            str = ""
    TWILIO_PHONE_NUMBER:          str = ""
    TWILIO_MESSAGING_SERVICE_SID: str = ""

    # ── Supabase ─────────────────────────────────────────────
    SUPABASE_URL:              str = ""
    SUPABASE_ANON_KEY:         str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_DB_PASSWORD:      str = ""

    # ── Cal.com ──────────────────────────────────────────────
    CALCOM_API_KEY:        str = ""
    CALCOM_API_URL:        str = "https://api.cal.com/v2"
    CALCOM_WEBHOOK_SECRET: str = ""

    # ── Google ───────────────────────────────────────────────
    GOOGLE_CLIENT_ID:      str = ""
    GOOGLE_CLIENT_SECRET:  str = ""
    GOOGLE_REDIRECT_URI:   str = "http://localhost:8080/auth/google/callback"
    GOOGLE_SCOPES:         str = "https://www.googleapis.com/auth/calendar"

    # ── Resend ───────────────────────────────────────────────
    RESEND_API_KEY:    str = ""
    RESEND_FROM_EMAIL: str = "rdv@agentlumy.com"

    # ── Google Cloud Run ─────────────────────────────────────
    GCP_PROJECT_ID:        str = ""
    GCP_REGION:            str = "europe-west1"
    GCP_SERVICE_NAME:      str = "voice-agent-garage-api"
    GCP_ARTIFACT_REGISTRY: str = "europe-west1-docker.pkg.dev"

    # ── RGPD : durées de conservation (en jours) ─────────────
    # Principe de minimisation : on ne garde une donnée personnelle que le temps
    # nécessaire. Passé ces délais, les données sont ANONYMISÉES et non
    # supprimées — les métadonnées non identifiantes (durée, statut, type de
    # demande) restent exploitables pour les statistiques du dashboard.
    #
    # ⚠️ Ces valeurs sont des défauts prudents, à valider avec le garage
    #    (responsable de traitement) et à inscrire dans son registre.
    RETENTION_RECORDINGS_DAYS:    int = 30    # enregistrements audio (le plus sensible)
    RETENTION_TRANSCRIPTS_DAYS:   int = 90    # transcriptions d'appels
    RETENTION_CALL_DETAILS_DAYS:  int = 365   # n° appelant, résumé
    RETENTION_NOTIFICATIONS_DAYS: int = 365   # contenu des SMS/emails envoyés
    RETENTION_INACTIVE_CLIENTS_DAYS: int = 1095   # 3 ans après le dernier contact

    # ── Tâches planifiées ────────────────────────────────────
    # Secret partagé avec Cloud Scheduler, exigé par les routes /internal/*.
    # Obligatoire en production : ces routes envoient des SMS.
    CRON_SECRET: str = ""

    # ── Mode fournisseurs ────────────────────────────────────
    # "real" = vrais appels API (nécessite les comptes payants)
    # "fake" = fournisseurs simulés au niveau HTTP : permet de valider tout le
    #          produit sans numéro Twilio FR, sans plan Cal.com et sans crédits.
    #          Voir app/integrations/fake_transport.py
    PROVIDER_MODE: str = "real"

    # ── Feature Flags ────────────────────────────────────────
    ENABLE_URGENCY_DETECTION:      bool = True
    ENABLE_CALL_RECORDING:         bool = True
    ENABLE_TRANSCRIPTION_STORAGE:  bool = True
    MAX_CALL_DURATION_SECONDS:     int  = 600

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def use_fake_providers(self) -> bool:
        """Fournisseurs externes simulés (aucun appel réseau, aucun coût)."""
        return self.PROVIDER_MODE.lower() == "fake"


@lru_cache
def get_settings() -> Settings:
    """Retourne les settings (singleton avec cache)."""
    return Settings()


# Instance globale
settings = get_settings()