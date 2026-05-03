"""
Client Supabase pour Voice Agent Garage
Gestion de la connexion, du multi-tenant et des opérations de base
"""
import logging
from contextlib import contextmanager
from typing import Optional
from uuid import UUID

from supabase import Client, create_client

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# CLIENT SUPABASE (Singleton)
# ============================================================

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Retourne le client Supabase (singleton).
    Utilise la service_role_key pour un accès complet côté backend.
    ⚠️  Ne jamais exposer ce client côté frontend.
    """
    global _supabase_client

    if _supabase_client is None:
        _supabase_client = create_client(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_SERVICE_ROLE_KEY,
        )
        logger.info("✅ Client Supabase initialisé")

    return _supabase_client


# Alias pratique
supabase: Client = None  # Initialisé au démarrage de l'app


def init_supabase() -> Client:
    """Initialise le client Supabase au démarrage de l'application FastAPI."""
    global supabase
    supabase = get_supabase_client()
    return supabase


# ============================================================
# CONTEXTE MULTI-TENANT
# ============================================================

@contextmanager
def garage_context(garage_id: UUID):
    """
    Context manager pour les opérations multi-tenant.
    Configure la variable de session PostgreSQL pour le RLS.

    Usage :
        with garage_context(garage_id):
            result = supabase.table("calls").select("*").execute()
    """
    client = get_supabase_client()

    try:
        # Définir le contexte du garage pour le RLS
        client.rpc(
            "set_config",
            {
                "setting": "app.current_garage_id",
                "value": str(garage_id),
                "is_local": True,
            }
        ).execute()

        logger.debug(f"🏢 Contexte garage défini : {garage_id}")
        yield client

    except Exception as e:
        logger.error(f"❌ Erreur contexte garage {garage_id} : {e}")
        raise
    finally:
        # Réinitialiser le contexte
        try:
            client.rpc(
                "set_config",
                {
                    "setting": "app.current_garage_id",
                    "value": "",
                    "is_local": True,
                }
            ).execute()
        except Exception:
            pass


# ============================================================
# REPOSITORY DE BASE (classe abstraite)
# ============================================================

class BaseRepository:
    """
    Classe de base pour tous les repositories.
    Fournit les opérations CRUD communes.
    """

    def __init__(self, table_name: str):
        self.table_name = table_name
        self.client = get_supabase_client()

    def _table(self):
        """Retourne le builder de table Supabase."""
        return self.client.table(self.table_name)

    def get_by_id(self, record_id: UUID) -> Optional[dict]:
        """Récupère un enregistrement par son ID."""
        try:
            result = (
                self._table()
                .select("*")
                .eq("id", str(record_id))
                .single()
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"❌ get_by_id {self.table_name}:{record_id} → {e}")
            return None

    def create(self, data: dict) -> Optional[dict]:
        """Crée un nouvel enregistrement."""
        try:
            result = (
                self._table()
                .insert(data)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"❌ create {self.table_name} → {e}")
            raise

    def update(self, record_id: UUID, data: dict) -> Optional[dict]:
        """Met à jour un enregistrement."""
        try:
            result = (
                self._table()
                .update(data)
                .eq("id", str(record_id))
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"❌ update {self.table_name}:{record_id} → {e}")
            raise

    def soft_delete(self, record_id: UUID) -> bool:
        """Soft delete (met deleted_at à NOW())."""
        try:
            self._table().update(
                {"deleted_at": "NOW()"}
            ).eq("id", str(record_id)).execute()
            return True
        except Exception as e:
            logger.error(f"❌ soft_delete {self.table_name}:{record_id} → {e}")
            return False

    def list_by_garage(
        self,
        garage_id: UUID,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "created_at",
        ascending: bool = False,
    ) -> list[dict]:
        """Liste les enregistrements d'un garage avec pagination."""
        try:
            result = (
                self._table()
                .select("*")
                .eq("garage_id", str(garage_id))
                .order(order_by, desc=not ascending)
                .range(offset, offset + limit - 1)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"❌ list_by_garage {self.table_name}:{garage_id} → {e}")
            return []