

"""
Moteur de génération dynamique des system prompts
Remplace les variables {{VAR}} par les vraies données du garage
"""
import logging
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# TYPES
# ============================================================

class GarageType(str, Enum):
    MECANIQUE_GENERALE  = "mecanique_generale"
    DEPANNEUR_REMORQUAGE = "depanneur_remorquage"
    CARROSSERIE         = "carrosserie"
    MIXTE               = "mixte"


PROMPT_TEMPLATES = {
    GarageType.MECANIQUE_GENERALE:   "garage_mecanique_v1.txt",
    GarageType.DEPANNEUR_REMORQUAGE: "depanneur_v1.txt",
    GarageType.CARROSSERIE:          "garage_mecanique_v1.txt",  # V2
    GarageType.MIXTE:                "garage_mecanique_v1.txt",  # V2
}

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ============================================================
# FORMATTEURS
# ============================================================

def format_business_hours(hours: dict) -> str:
    """
    Convertit le JSONB business_hours en texte lisible pour le prompt.

    Input:
        {"monday": {"open": "08:00", "close": "18:00", "closed": false}, ...}

    Output:
        "Lundi au vendredi : 8h-18h | Samedi : 8h-12h | Dimanche : fermé"
    """
    DAY_NAMES = {
        "monday":    "Lundi",
        "tuesday":   "Mardi",
        "wednesday": "Mercredi",
        "thursday":  "Jeudi",
        "friday":    "Vendredi",
        "saturday":  "Samedi",
        "sunday":    "Dimanche",
    }

    parts = []
    for day_key, day_name in DAY_NAMES.items():
        day = hours.get(day_key, {})
        if day.get("closed"):
            parts.append(f"{day_name} : fermé")
        elif day.get("open") and day.get("close"):
            open_h  = day["open"].replace(":00", "h").replace(":30", "h30")
            close_h = day["close"].replace(":00", "h").replace(":30", "h30")
            parts.append(f"{day_name} : {open_h}-{close_h}")

    # Compresser les jours consécutifs avec les mêmes horaires
    # ex: "Lundi : 8h-18h | Mardi : 8h-18h | ..." → "Lundi au vendredi : 8h-18h"
    return " | ".join(parts)


def format_services_list(services: list[dict]) -> str:
    """
    Convertit la liste des services en texte lisible.

    Input:
        [{"name": "Révision", "duration_minutes": 90}, ...]

    Output:
        "Révision complète (1h30), Vidange (45min), Freins (1h)..."
    """
    if not services:
        return "Mécanique générale, entretien, réparation"

    formatted = []
    for service in services[:8]:  # Max 8 services dans le prompt
        name     = service.get("name", "")
        duration = service.get("duration_minutes", 60)

        # Formater la durée
        if duration < 60:
            dur_str = f"{duration}min"
        elif duration == 60:
            dur_str = "1h"
        else:
            hours   = duration // 60
            minutes = duration % 60
            dur_str = f"{hours}h{minutes:02d}" if minutes else f"{hours}h"

        formatted.append(f"{name} ({dur_str})")

    return ", ".join(formatted)


def format_is_24_7(business_hours: dict) -> str:
    """Détermine si le service est 24/7."""
    for day in business_hours.values():
        if day.get("closed"):
            return "du lundi au samedi (24h/24 sur intervention urgente)"
    return "7j/7, 24h/24"


# ============================================================
# GÉNÉRATEUR PRINCIPAL
# ============================================================

class PromptGenerator:
    """
    Génère les system prompts dynamiques pour chaque garage.

    Usage:
        generator = PromptGenerator()
        prompt = generator.generate(garage_data, services)
    """

    def __init__(self):
        self._cache: dict[str, str] = {}

    def _load_template(self, garage_type: GarageType) -> str:
        """Charge le template depuis le fichier."""
        template_file = PROMPT_TEMPLATES.get(garage_type)
        if not template_file:
            template_file = "garage_mecanique_v1.txt"

        template_path = TEMPLATES_DIR / template_file

        # Cache en mémoire
        if str(template_path) not in self._cache:
            if not template_path.exists():
                raise FileNotFoundError(
                    f"Template introuvable : {template_path}"
                )
            self._cache[str(template_path)] = template_path.read_text(
                encoding="utf-8"
            )
            logger.debug(f"📄 Template chargé : {template_file}")

        return self._cache[str(template_path)]

    def generate(
        self,
        garage_data: dict,
        services: list[dict],
        custom_overrides: Optional[dict] = None,
    ) -> str:
        """
        Génère le system prompt complet pour un garage.

        Args:
            garage_data     : Dict avec les données du garage (depuis Supabase)
            services        : Liste des services actifs du garage
            custom_overrides: Variables supplémentaires à injecter

        Returns:
            str : Le system prompt complet avec toutes les variables remplacées
        """
        garage_type = GarageType(
            garage_data.get("garage_type", "mecanique_generale")
        )

        # Charger le template de base
        template = self._load_template(garage_type)

        # Formater les données
        business_hours = garage_data.get("business_hours", {})

        # Construire les variables de remplacement
        variables = {
            "AGENT_NAME":    garage_data.get("agent_name", "Léa"),
            "GARAGE_NAME":   garage_data.get("name", "le garage"),
            "GARAGE_ADDRESS": garage_data.get("address_street", ""),
            "GARAGE_CITY":   garage_data.get("address_city", ""),
            "GARAGE_PHONE":  garage_data.get("phone_number", ""),
            "GARAGE_EMAIL":  garage_data.get("email", ""),
            "TRANSFER_PHONE": garage_data.get("transfer_phone_number", ""),
            "BUSINESS_HOURS": format_business_hours(business_hours),
            "SERVICES_LIST": format_services_list(services),
            "IS_24_7":       format_is_24_7(business_hours),
        }

        # Ajouter les overrides custom si fournis
        if custom_overrides:
            variables.update(custom_overrides)

        # Remplacer toutes les variables dans le template
        prompt = template
        for key, value in variables.items():
            prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

        # Nettoyer les lignes de commentaires (commençant par #)
        lines  = prompt.split("\n")
        lines  = [l for l in lines if not l.strip().startswith("#")]
        prompt = "\n".join(lines).strip()

        logger.info(
            f"✅ Prompt généré pour {garage_data.get('name')} "
            f"({garage_type}) — {len(prompt)} caractères"
        )

        return prompt

    def generate_first_message(self, garage_data: dict) -> str:
        """
        Génère le premier message que l'agent prononce
        quand il décroche l'appel.

        Conformité (AI Act / CNIL) :
        - annoncer qu'il s'agit d'un assistant vocal (IA), pas d'un humain
        - mentionner l'enregistrement si celui-ci est activé
        """
        from app.config import settings

        agent_name  = garage_data.get("agent_name", "Léa")
        garage_name = garage_data.get("name", "le garage")

        recording_notice = (
            " Cet appel peut être enregistré."
            if settings.ENABLE_CALL_RECORDING
            else ""
        )

        return (
            f"Bonjour, je suis {agent_name}, l'assistante vocale de "
            f"{garage_name}.{recording_notice} Comment puis-je vous aider ?"
        )

    def invalidate_cache(self):
        """Vide le cache (utile après modification d'un template)."""
        self._cache.clear()
        logger.info("🗑️ Cache des prompts vidé")


# ============================================================
# INSTANCE GLOBALE
# ============================================================
prompt_generator = PromptGenerator()


def generate_system_prompt(
    garage_type: str,
    garage_name: str,
    agent_name: str,
    phone: str,
    address: Optional[str] = None,
    city: Optional[str] = None,
    owner_name: Optional[str] = None,
    services: list = None,
    schedule: dict = None,
    calcom_username: Optional[str] = None,
    transfer_phone: Optional[str] = None,
    timezone: str = "Europe/Paris",
) -> str:

    # Convertir le schedule onboarding → format business_hours
    # Onboarding : {"monday": [{"start": "08:00", "end": "18:00"}]}
    # business_hours : {"monday": {"open": "08:00", "close": "18:00", "closed": False}}
    business_hours = {}
    for day, slots in (schedule or {}).items():
        if slots:
            business_hours[day] = {
                "open":   slots[0].start if hasattr(slots[0], "start") else slots[0]["start"],
                "close":  slots[0].end   if hasattr(slots[0], "end")   else slots[0]["end"],
                "closed": False,
            }
        else:
            business_hours[day] = {"closed": True}

    garage_data = {
        "garage_type":           garage_type,
        "name":                  garage_name,
        "agent_name":            agent_name,
        "phone_number":          phone,
        "address_street":        address or "",
        "address_city":          city or "",
        "email":                 "",
        "transfer_phone_number": transfer_phone or "",
        "business_hours":        business_hours,
        "owner_name":            owner_name or "",
        "timezone":              timezone,
    }

    # services peut être List[str] ou List[dict]
    services_dicts = []
    for s in (services or []):
        if isinstance(s, str):
            services_dicts.append({"name": s, "duration_minutes": 60})
        else:
            services_dicts.append(s)

    return prompt_generator.generate(
        garage_data=garage_data,
        services=services_dicts,
        custom_overrides={"CALCOM_USERNAME": calcom_username or ""},
    )


# ============================================================
# UTILITAIRE : RÉCUPÉRER LE PROMPT D'UN GARAGE DEPUIS LA BDD
# ============================================================

async def get_prompt_for_garage(garage_id: UUID) -> tuple[str, str]:
    """
    Récupère ou génère le system prompt pour un garage donné.

    Ordre de priorité :
    1. Prompt custom enregistré en BDD (agent_prompts table)
    2. Prompt généré dynamiquement depuis les données du garage

    Returns:
        tuple[str, str] : (system_prompt, first_message)
    """
    from app.db.supabase_client import get_supabase_client

    client = get_supabase_client()

    # 1. Chercher un prompt custom actif en BDD
    try:
        custom = (
            client.table("agent_prompts")
            .select("system_prompt, first_message")
            .eq("garage_id", str(garage_id))
            .eq("is_active", True)
            .single()
            .execute()
        )

        if custom.data:
            logger.info(f"📝 Prompt custom trouvé pour garage {garage_id}")
            return (
                custom.data["system_prompt"],
                custom.data.get("first_message", "Bonjour, comment puis-je vous aider ?")
            )
    except Exception:
        pass  # Pas de prompt custom, on génère dynamiquement

    # 2. Générer dynamiquement depuis les données du garage
    garage = (
        client.table("garages")
        .select("*")
        .eq("id", str(garage_id))
        .single()
        .execute()
    )

    if not garage.data:
        raise ValueError(f"Garage introuvable : {garage_id}")

    services = (
        client.table("garage_services")
        .select("name, duration_minutes")
        .eq("garage_id", str(garage_id))
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )

    system_prompt  = prompt_generator.generate(
        garage_data=garage.data,
        services=services.data or [],
    )
    first_message = prompt_generator.generate_first_message(garage.data)

    return system_prompt, first_message