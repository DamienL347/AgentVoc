-- AgentLumy — Schéma Supabase (export SQL Editor)
-- NE PAS ÉDITER À LA MAIN : modifier la base puis relancer l'export.

-- ============================ TYPES ÉNUMÉRÉS ============================
CREATE TYPE public.appointment_status AS ENUM ('propose', 'confirme', 'annule', 'modifie', 'complete', 'no_show');
CREATE TYPE public.call_status AS ENUM ('rdv_pris', 'rdv_modifie', 'rdv_annule', 'information_donnee', 'devis_propose', 'transfere_humain', 'urgence_signalee', 'message_laisse', 'abandonne', 'erreur');
CREATE TYPE public.demand_type AS ENUM ('prise_rdv', 'information', 'devis', 'modification_rdv', 'annulation_rdv', 'depannage_urgent', 'depannage_non_urgent', 'reclamation', 'autre');
CREATE TYPE public.fuel_type AS ENUM ('essence', 'diesel', 'hybride', 'electrique', 'gpl', 'autre');
CREATE TYPE public.garage_status AS ENUM ('active', 'suspended', 'trial', 'churned');
CREATE TYPE public.garage_type AS ENUM ('mecanique_generale', 'depanneur_remorquage', 'carrosserie', 'mixte');
CREATE TYPE public.notification_channel AS ENUM ('sms', 'email', 'whatsapp', 'push');
CREATE TYPE public.notification_status AS ENUM ('pending', 'sent', 'delivered', 'failed');
CREATE TYPE public.urgency_level AS ENUM ('faible', 'moyenne', 'elevee', 'critique');

-- ================================ TABLES ================================

CREATE TABLE public.agent_prompts (
    id uuid DEFAULT uuid_generate_v4() NOT NULL,
    garage_id uuid NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    is_active boolean DEFAULT true,
    system_prompt text NOT NULL,
    first_message text,
    created_at timestamp with time zone DEFAULT now(),
    created_by character varying(255),
    CONSTRAINT agent_prompts_pkey PRIMARY KEY (id),
    CONSTRAINT agent_prompts_garage_id_fkey FOREIGN KEY (garage_id) REFERENCES garages(id) ON DELETE CASCADE
);

CREATE TABLE public.appointments (
    id uuid DEFAULT uuid_generate_v4() NOT NULL,
    garage_id uuid NOT NULL,
    end_client_id uuid,
    vehicle_id uuid,
    call_id uuid,
    service_id uuid,
    calcom_booking_id character varying(255),
    calcom_booking_uid character varying(255),
    google_event_id character varying(255),
    scheduled_at timestamp with time zone NOT NULL,
    duration_minutes integer DEFAULT 60,
    ends_at timestamp with time zone,
    title character varying(255),
    description text,
    status appointment_status DEFAULT 'confirme'::appointment_status,
    client_name character varying(255),
    client_phone character varying(20),
    client_email character varying(255),
    vehicle_brand character varying(100),
    vehicle_model character varying(100),
    vehicle_registration character varying(20),
    original_scheduled_at timestamp with time zone,
    cancellation_reason text,
    cancelled_at timestamp with time zone,
    cancelled_by character varying(50),
    reminder_24h_sent boolean DEFAULT false,
    reminder_2h_sent boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT appointments_pkey PRIMARY KEY (id),
    CONSTRAINT appointments_call_id_fkey FOREIGN KEY (call_id) REFERENCES calls(id) ON DELETE SET NULL,
    CONSTRAINT appointments_end_client_id_fkey FOREIGN KEY (end_client_id) REFERENCES end_clients(id) ON DELETE SET NULL,
    CONSTRAINT appointments_garage_id_fkey FOREIGN KEY (garage_id) REFERENCES garages(id) ON DELETE CASCADE,
    CONSTRAINT appointments_service_id_fkey FOREIGN KEY (service_id) REFERENCES garage_services(id) ON DELETE SET NULL,
    CONSTRAINT appointments_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL
);

CREATE TABLE public.audit_logs (
    id bigint DEFAULT nextval('audit_logs_id_seq'::regclass) NOT NULL,
    garage_id uuid,
    table_name character varying(100) NOT NULL,
    record_id uuid,
    action character varying(20) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_fields text[],
    performed_by character varying(255),
    performed_at timestamp with time zone DEFAULT now(),
    ip_address inet,
    CONSTRAINT audit_logs_pkey PRIMARY KEY (id),
    CONSTRAINT audit_logs_garage_id_fkey FOREIGN KEY (garage_id) REFERENCES garages(id) ON DELETE SET NULL
);

CREATE TABLE public.calls (
    id uuid DEFAULT uuid_generate_v4() NOT NULL,
    garage_id uuid NOT NULL,
    end_client_id uuid,
    vehicle_id uuid,
    vapi_call_id character varying(255),
    twilio_call_sid character varying(255),
    caller_phone character varying(20) NOT NULL,
    called_phone character varying(20),
    demand_type demand_type,
    urgency_level urgency_level DEFAULT 'faible'::urgency_level,
    call_status call_status,
    started_at timestamp with time zone,
    ended_at timestamp with time zone,
    duration_seconds integer,
    transcription text,
    summary text,
    detected_keywords text[],
    collected_data jsonb DEFAULT '{}'::jsonb,
    appointment_id uuid,
    transfer_triggered boolean DEFAULT false,
    transfer_reason text,
    confidence_score double precision,
    fallback_triggered boolean DEFAULT false,
    recording_url text,
    recording_duration_sec integer,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT calls_vapi_call_id_key UNIQUE (vapi_call_id),
    CONSTRAINT calls_pkey PRIMARY KEY (id),
    CONSTRAINT calls_end_client_id_fkey FOREIGN KEY (end_client_id) REFERENCES end_clients(id) ON DELETE SET NULL,
    CONSTRAINT calls_garage_id_fkey FOREIGN KEY (garage_id) REFERENCES garages(id) ON DELETE CASCADE,
    CONSTRAINT calls_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL,
    CONSTRAINT fk_calls_appointment FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL
);

CREATE TABLE public.end_clients (
    id uuid DEFAULT uuid_generate_v4() NOT NULL,
    garage_id uuid NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    full_name character varying(255),
    phone_number character varying(20) NOT NULL,
    email character varying(255),
    total_calls integer DEFAULT 0,
    total_appointments integer DEFAULT 0,
    last_call_at timestamp with time zone,
    last_appointment_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT end_clients_garage_id_phone_number_key UNIQUE (garage_id, phone_number),
    CONSTRAINT end_clients_pkey PRIMARY KEY (id),
    CONSTRAINT end_clients_garage_id_fkey FOREIGN KEY (garage_id) REFERENCES garages(id) ON DELETE CASCADE
);

CREATE TABLE public.garage_services (
    id uuid DEFAULT uuid_generate_v4() NOT NULL,
    garage_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    duration_minutes integer DEFAULT 60 NOT NULL,
    price_indicative numeric(10,2),
    price_display boolean DEFAULT false,
    is_urgent_eligible boolean DEFAULT false,
    is_active boolean DEFAULT true,
    sort_order integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT garage_services_pkey PRIMARY KEY (id),
    CONSTRAINT garage_services_garage_id_fkey FOREIGN KEY (garage_id) REFERENCES garages(id) ON DELETE CASCADE
);

CREATE TABLE public.garages (
    id uuid DEFAULT uuid_generate_v4() NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(100) NOT NULL,
    garage_type garage_type DEFAULT 'mecanique_generale'::garage_type NOT NULL,
    status garage_status DEFAULT 'trial'::garage_status NOT NULL,
    phone_number character varying(20) NOT NULL,
    agent_phone_number character varying(20),
    email character varying(255),
    website character varying(500),
    address_street character varying(255),
    address_city character varying(100),
    address_zip character varying(10),
    address_country character varying(2) DEFAULT 'FR'::character varying,
    vapi_assistant_id character varying(255),
    calcom_user_id character varying(255),
    google_calendar_id character varying(255),
    google_refresh_token text,
    agent_name character varying(100) DEFAULT 'Aria'::character varying,
    agent_voice_id character varying(255),
    business_hours jsonb DEFAULT '{"friday": {"open": "08:00", "close": "18:00", "closed": false}, "monday": {"open": "08:00", "close": "18:00", "closed": false}, "sunday": {"open": null, "close": null, "closed": true}, "tuesday": {"open": "08:00", "close": "18:00", "closed": false}, "saturday": {"open": "08:00", "close": "12:00", "closed": false}, "thursday": {"open": "08:00", "close": "18:00", "closed": false}, "wednesday": {"open": "08:00", "close": "18:00", "closed": false}}'::jsonb,
    transfer_phone_number character varying(20),
    transfer_sms_number character varying(20),
    plan character varying(50) DEFAULT 'starter'::character varying,
    trial_ends_at timestamp with time zone,
    subscription_starts_at timestamp with time zone,
    monthly_price_eur numeric(10,2) DEFAULT 299.00,
    onboarded_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    deleted_at timestamp with time zone,
    twilio_phone_number text,
    twilio_phone_sid text,
    vapi_phone_number_id text,
    calcom_username text,
    calcom_event_type_id integer,
    onboarding_status text DEFAULT 'pending'::text NOT NULL,
    onboarding_completed_at timestamp with time zone,
    onboarding_error text,
    CONSTRAINT garages_slug_key UNIQUE (slug),
    CONSTRAINT garages_pkey PRIMARY KEY (id)
);

CREATE TABLE public.notifications (
    id uuid DEFAULT uuid_generate_v4() NOT NULL,
    garage_id uuid NOT NULL,
    call_id uuid,
    appointment_id uuid,
    recipient_type character varying(20) NOT NULL,
    recipient_phone character varying(20),
    recipient_email character varying(255),
    channel notification_channel NOT NULL,
    subject character varying(255),
    body text NOT NULL,
    status notification_status DEFAULT 'pending'::notification_status,
    sent_at timestamp with time zone,
    delivered_at timestamp with time zone,
    error_message text,
    twilio_message_sid character varying(255),
    resend_email_id character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT notifications_pkey PRIMARY KEY (id),
    CONSTRAINT notifications_appointment_id_fkey FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
    CONSTRAINT notifications_call_id_fkey FOREIGN KEY (call_id) REFERENCES calls(id) ON DELETE SET NULL,
    CONSTRAINT notifications_garage_id_fkey FOREIGN KEY (garage_id) REFERENCES garages(id) ON DELETE CASCADE
);

CREATE TABLE public.onboarding_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    garage_id uuid NOT NULL,
    step text NOT NULL,
    status text NOT NULL,
    details jsonb,
    error_message text,
    duration_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT onboarding_logs_pkey PRIMARY KEY (id),
    CONSTRAINT onboarding_logs_garage_id_fkey FOREIGN KEY (garage_id) REFERENCES garages(id) ON DELETE CASCADE
);

CREATE TABLE public.vehicles (
    id uuid DEFAULT uuid_generate_v4() NOT NULL,
    garage_id uuid NOT NULL,
    end_client_id uuid,
    brand character varying(100),
    model character varying(100),
    year integer,
    registration_plate character varying(20),
    fuel_type fuel_type,
    mileage integer,
    color character varying(50),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT vehicles_pkey PRIMARY KEY (id),
    CONSTRAINT vehicles_end_client_id_fkey FOREIGN KEY (end_client_id) REFERENCES end_clients(id) ON DELETE SET NULL,
    CONSTRAINT vehicles_garage_id_fkey FOREIGN KEY (garage_id) REFERENCES garages(id) ON DELETE CASCADE
);

-- ================================ INDEX =================================
CREATE INDEX idx_appointments_calcom ON public.appointments USING btree (calcom_booking_uid);
CREATE INDEX idx_appointments_client ON public.appointments USING btree (end_client_id);
CREATE INDEX idx_appointments_garage_id ON public.appointments USING btree (garage_id);
CREATE INDEX idx_appointments_scheduled ON public.appointments USING btree (garage_id, scheduled_at);
CREATE INDEX idx_appointments_status ON public.appointments USING btree (garage_id, status);
CREATE INDEX idx_audit_logs_garage_id ON public.audit_logs USING btree (garage_id);
CREATE INDEX idx_audit_logs_performed_at ON public.audit_logs USING btree (performed_at DESC);
CREATE INDEX idx_audit_logs_table_record ON public.audit_logs USING btree (table_name, record_id);
CREATE INDEX idx_calls_caller_phone ON public.calls USING btree (garage_id, caller_phone);
CREATE INDEX idx_calls_created_at ON public.calls USING btree (garage_id, created_at DESC);
CREATE INDEX idx_calls_garage_id ON public.calls USING btree (garage_id);
CREATE INDEX idx_calls_status ON public.calls USING btree (garage_id, call_status);
CREATE INDEX idx_calls_urgency ON public.calls USING btree (garage_id, urgency_level) WHERE (urgency_level = ANY (ARRAY['elevee'::urgency_level, 'critique'::urgency_level]));
CREATE INDEX idx_calls_vapi_id ON public.calls USING btree (vapi_call_id);
CREATE INDEX idx_end_clients_garage_id ON public.end_clients USING btree (garage_id);
CREATE INDEX idx_end_clients_name_trgm ON public.end_clients USING gin (full_name gin_trgm_ops);
CREATE INDEX idx_end_clients_phone ON public.end_clients USING btree (garage_id, phone_number);
CREATE INDEX idx_garage_services_active ON public.garage_services USING btree (garage_id, is_active);
CREATE INDEX idx_garage_services_garage_id ON public.garage_services USING btree (garage_id);
CREATE INDEX idx_garages_agent_phone ON public.garages USING btree (agent_phone_number);
CREATE INDEX idx_garages_slug ON public.garages USING btree (slug);
CREATE INDEX idx_garages_status ON public.garages USING btree (status) WHERE (deleted_at IS NULL);
CREATE UNIQUE INDEX idx_garages_twilio_phone ON public.garages USING btree (twilio_phone_number) WHERE (twilio_phone_number IS NOT NULL);
CREATE UNIQUE INDEX idx_garages_vapi_assistant ON public.garages USING btree (vapi_assistant_id) WHERE (vapi_assistant_id IS NOT NULL);
CREATE INDEX idx_notifications_garage_id ON public.notifications USING btree (garage_id);
CREATE INDEX idx_notifications_status ON public.notifications USING btree (status) WHERE (status = 'pending'::notification_status);
CREATE INDEX idx_onboarding_logs_garage ON public.onboarding_logs USING btree (garage_id, created_at DESC);
CREATE INDEX idx_vehicles_client_id ON public.vehicles USING btree (end_client_id);
CREATE INDEX idx_vehicles_garage_id ON public.vehicles USING btree (garage_id);
CREATE INDEX idx_vehicles_registration ON public.vehicles USING btree (garage_id, registration_plate);

-- ============================== FONCTIONS ===============================
CREATE OR REPLACE FUNCTION public.calculate_ends_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.scheduled_at IS NOT NULL AND NEW.duration_minutes IS NOT NULL THEN
        NEW.ends_at = NEW.scheduled_at + (NEW.duration_minutes * INTERVAL '1 minute');
    END IF;
    RETURN NEW;
END;
$function$
;

CREATE OR REPLACE FUNCTION public.generate_garage_slug(garage_name text)
 RETURNS text
 LANGUAGE plpgsql
AS $function$
DECLARE
    base_slug  TEXT;
    final_slug TEXT;
    counter    INTEGER := 0;
BEGIN
    base_slug  := lower(unaccent(garage_name));
    base_slug  := regexp_replace(base_slug, '[^a-z0-9\s-]', '', 'g');
    base_slug  := regexp_replace(base_slug, '\s+', '-', 'g');
    base_slug  := regexp_replace(base_slug, '-+', '-', 'g');
    base_slug  := trim(both '-' from base_slug);
    final_slug := base_slug;

    WHILE EXISTS (SELECT 1 FROM garages WHERE slug = final_slug) LOOP
        counter    := counter + 1;
        final_slug := base_slug || '-' || counter;
    END LOOP;

    RETURN final_slug;
END;
$function$
;

-- Corrigee le 14/08/2026 (cf. scripts/fix_get_garage_by_phone.sql) : la version
-- d'origine selectionnait g.timezone et g.is_active, colonnes inexistantes, et
-- echouait donc a chaque appel entrant.
CREATE OR REPLACE FUNCTION public.get_garage_by_phone(p_phone text)
 RETURNS TABLE(id uuid, name text, garage_type text, status text, vapi_assistant_id text, calcom_username text, calcom_event_type_id integer, owner_phone text, owner_email text, transfer_phone_number text, transfer_sms_number text, business_hours jsonb)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
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
$function$
;

CREATE OR REPLACE FUNCTION public.get_garage_stats(p_garage_id uuid, p_start_date timestamp with time zone DEFAULT (now() - '30 days'::interval), p_end_date timestamp with time zone DEFAULT now())
 RETURNS TABLE(total_calls bigint, calls_rdv_pris bigint, calls_transferes bigint, calls_urgences bigint, calls_abandonnes bigint, conversion_rate_pct numeric, total_appointments bigint, avg_call_duration_sec numeric)
 LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)                                                AS total_calls,
        COUNT(*) FILTER (WHERE c.call_status = 'rdv_pris')     AS calls_rdv_pris,
        COUNT(*) FILTER (WHERE c.transfer_triggered = TRUE)    AS calls_transferes,
        COUNT(*) FILTER (WHERE c.urgency_level IN ('elevee','critique')) AS calls_urgences,
        COUNT(*) FILTER (WHERE c.call_status = 'abandonne')    AS calls_abandonnes,
        ROUND(
            COUNT(*) FILTER (WHERE c.call_status = 'rdv_pris')::NUMERIC
            / NULLIF(COUNT(*), 0) * 100, 1
        )                                                       AS conversion_rate_pct,
        (
            SELECT COUNT(*) FROM appointments a
            WHERE  a.garage_id   = p_garage_id
              AND  a.created_at  BETWEEN p_start_date AND p_end_date
              AND  a.status     != 'annule'
        )                                                       AS total_appointments,
        ROUND(AVG(c.duration_seconds), 0)                      AS avg_call_duration_sec
    FROM calls c
    WHERE c.garage_id  = p_garage_id
      AND c.created_at BETWEEN p_start_date AND p_end_date;
END;
$function$
;

CREATE OR REPLACE FUNCTION public.update_client_stats_after_appointment()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.end_client_id IS NOT NULL AND NEW.status = 'confirme' THEN
        UPDATE end_clients
        SET
            total_appointments  = total_appointments + 1,
            last_appointment_at = NOW()
        WHERE id = NEW.end_client_id;
    END IF;
    RETURN NEW;
END;
$function$
;

CREATE OR REPLACE FUNCTION public.update_client_stats_after_call()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.end_client_id IS NOT NULL THEN
        UPDATE end_clients
        SET
            total_calls  = total_calls + 1,
            last_call_at = NOW()
        WHERE id = NEW.end_client_id;
    END IF;
    RETURN NEW;
END;
$function$
;

CREATE OR REPLACE FUNCTION public.update_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$
;


-- =============================== TRIGGERS ===============================
CREATE TRIGGER trg_appointments_updated_at BEFORE UPDATE ON public.appointments FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_calculate_ends_at BEFORE INSERT OR UPDATE ON public.appointments FOR EACH ROW EXECUTE FUNCTION calculate_ends_at();
CREATE TRIGGER trg_calls_updated_at BEFORE UPDATE ON public.calls FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_end_clients_updated_at BEFORE UPDATE ON public.end_clients FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_garage_services_updated_at BEFORE UPDATE ON public.garage_services FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_garages_updated_at BEFORE UPDATE ON public.garages FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_update_client_stats_after_appointment AFTER INSERT ON public.appointments FOR EACH ROW EXECUTE FUNCTION update_client_stats_after_appointment();
CREATE TRIGGER trg_update_client_stats_after_call AFTER INSERT ON public.calls FOR EACH ROW EXECUTE FUNCTION update_client_stats_after_call();
CREATE TRIGGER trg_vehicles_updated_at BEFORE UPDATE ON public.vehicles FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ================================ VUES ==================================
CREATE OR REPLACE VIEW public.v_onboarding_status AS
 SELECT id,
    name,
    email,
    phone_number,
    onboarding_status,
    twilio_phone_number,
    vapi_assistant_id,
    calcom_username,
    onboarding_completed_at,
    onboarding_error,
    created_at,
    ( SELECT (ol.step || ' → '::text) || ol.status
           FROM onboarding_logs ol
          WHERE ol.garage_id = g.id
          ORDER BY ol.created_at DESC
         LIMIT 1) AS last_step
   FROM garages g
  ORDER BY created_at DESC;

-- ========================= ROW LEVEL SECURITY ===========================
ALTER TABLE public.agent_prompts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.end_clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.garage_services ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.garages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.onboarding_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicles ENABLE ROW LEVEL SECURITY;
CREATE POLICY service_role_appointments ON public.appointments FOR ALL
    USING ((auth.role() = 'service_role'::text));
CREATE POLICY service_role_calls ON public.calls FOR ALL
    USING ((auth.role() = 'service_role'::text));
CREATE POLICY service_role_clients ON public.end_clients FOR ALL
    USING ((auth.role() = 'service_role'::text));
CREATE POLICY service_role_garages ON public.garages FOR ALL
    USING ((auth.role() = 'service_role'::text));
CREATE POLICY service_role_notifs ON public.notifications FOR ALL
    USING ((auth.role() = 'service_role'::text));
CREATE POLICY service_role_prompts ON public.agent_prompts FOR ALL
    USING ((auth.role() = 'service_role'::text));
CREATE POLICY service_role_services ON public.garage_services FOR ALL
    USING ((auth.role() = 'service_role'::text));
CREATE POLICY service_role_vehicles ON public.vehicles FOR ALL
    USING ((auth.role() = 'service_role'::text));
