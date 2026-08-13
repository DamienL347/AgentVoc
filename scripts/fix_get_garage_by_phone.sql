-- ─────────────────────────────────────────────────────────────────────────────
-- CORRECTIF BLOQUANT — get_garage_by_phone()
--
-- Symptôme : tout appel entrant échoue à identifier son garage.
--   ERROR 42703: column g.timezone does not exist
--
-- Cause : la fonction (résolveur de tenant, appelée par
-- app/middleware/tenant_resolver.py) sélectionne trois colonnes qui n'existent
-- pas dans `garages` :
--   • g.timezone   → n'a jamais existé
--   • g.is_active  → la colonne réelle est `status` (enum garage_status)
--   • g.garage_type était déclaré `text` alors que c'est un enum (erreur de type)
--
-- Le bug était invisible : le middleware avale l'exception pour ne jamais bloquer
-- un appel, et se contente d'un log « Aucun garage trouvé ».
--
-- Effet du correctif : la résolution renvoie les garages `active` ET `trial`
-- (les garages onboardés démarrent en `trial` — filtrer sur « actif » seul les
-- aurait tous exclus), en excluant les garages supprimés.
--
-- À exécuter dans : Supabase → SQL Editor → Run
-- ─────────────────────────────────────────────────────────────────────────────

-- Le type de retour change : il faut supprimer avant de recréer.
DROP FUNCTION IF EXISTS public.get_garage_by_phone(text);

CREATE FUNCTION public.get_garage_by_phone(p_phone text)
RETURNS TABLE(
    id                    uuid,
    name                  text,
    garage_type           text,
    status                text,
    vapi_assistant_id     text,
    calcom_username       text,
    calcom_event_type_id  integer,
    owner_phone           text,
    owner_email           text,
    transfer_phone_number text,
    transfer_sms_number   text,
    business_hours        jsonb
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public          -- SECURITY DEFINER sans search_path figé = risque d'escalade
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        g.id,
        g.name::text,
        g.garage_type::text,
        g.status::text,
        g.vapi_assistant_id::text,
        g.calcom_username::text,
        g.calcom_event_type_id,
        g.phone_number::text,
        g.email::text,
        g.transfer_phone_number::text,
        g.transfer_sms_number::text,
        g.business_hours
    FROM garages g
    WHERE g.twilio_phone_number = p_phone
      AND g.deleted_at IS NULL
      AND g.status IN ('active', 'trial');
END;
$function$;

-- Vérification (doit renvoyer une ligne pour un garage onboardé) :
-- SELECT * FROM get_garage_by_phone('+14722383374');
