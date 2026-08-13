# ─────────────────────────────────────────────────────────────────────────────
# AgentLumy — Dashboard de monitoring
# Lancer : streamlit run dashboard.py
#
# Charte : carbone + ambre (alignée sur portfolio/site/index.html).
# Couleurs de séries, formes de graphiques et règles d'accessibilité :
# voir dashboard_theme.py
# ─────────────────────────────────────────────────────────────────────────────

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

import dashboard_theme as T

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AgentLumy — Dashboard",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(T.CSS, unsafe_allow_html=True)

# ─── Libellés métier (les ENUMs Supabase sont en français) ───────────────────
CALL_STATUS_LABELS = {
    "rdv_pris":           "RDV pris",
    "rdv_modifie":        "RDV modifié",
    "rdv_annule":         "RDV annulé",
    "information_donnee": "Information donnée",
    "devis_propose":      "Devis proposé",
    "message_laisse":     "Message laissé",
    "transfere_humain":   "Transféré au patron",
    "urgence_signalee":   "Urgence signalée",
    "abandonne":          "Abandonné",
    "erreur":             "Erreur technique",
}
# Ce qui compte comme un appel « raté » côté métier
CALL_STATUS_ECHEC = {"abandonne", "erreur"}

APPT_STATUS_LABELS = {
    "propose":  "Proposé",   "confirme": "Confirmé", "modifie": "Modifié",
    "annule":   "Annulé",    "complete": "Terminé",  "no_show": "Non présenté",
}
# Statuts de RDV = états, pas des séries : palette de statut réservée
APPT_STATUS_COLORS = {
    "Confirmé":     T.GOOD,
    "Terminé":      T.SERIES[2],
    "Modifié":      T.SERIES[4],
    "Proposé":      T.WARNING,
    "Annulé":       T.CRITICAL,
    "Non présenté": T.SERIOUS,
}

URGENCE_FORTE = {"critique", "elevee"}
OBJECTIF_CONVERSION = 30.0


# ─── Connexion Supabase ───────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    # Service role key pour bypasser RLS et tout lire
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        st.error("SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquants dans .env")
        st.stop()
    return create_client(url, key)

supabase = get_supabase()


# ─── Loaders (cache 60s) ──────────────────────────────────────────────────────
def _since(days):
    """Borne basse ISO, ou None pour tout l'historique."""
    if days is None:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

@st.cache_data(ttl=60)
def load_garages():
    res = supabase.table("garages") \
        .select("id, name, garage_type, status, onboarding_status, twilio_phone_number, created_at") \
        .order("name") \
        .execute()
    return pd.DataFrame(res.data or [])

def _scoped(table, garage_id, days):
    q = supabase.table(table).select("*")
    since = _since(days)
    if since:
        q = q.gte("created_at", since)
    if garage_id:
        q = q.eq("garage_id", garage_id)
    return pd.DataFrame(q.execute().data or [])

@st.cache_data(ttl=60)
def load_calls(garage_id, days):
    df = _scoped("calls", garage_id, days)
    if not df.empty:
        # started_at = date réelle de l'appel ; created_at = date d'insertion (fallback)
        base = df["started_at"] if "started_at" in df.columns else df["created_at"]
        df["dt"] = pd.to_datetime(base.fillna(df["created_at"]), format="ISO8601", utc=True)
        df = df.sort_values("dt", ascending=False)
    return df

@st.cache_data(ttl=60)
def load_appointments(garage_id, days):
    df = _scoped("appointments", garage_id, days)
    if not df.empty:
        df["dt"] = pd.to_datetime(df["created_at"], format="ISO8601", utc=True)
        df = df.sort_values("dt", ascending=False)
    return df

@st.cache_data(ttl=60)
def load_notifications(garage_id, days):
    return _scoped("notifications", garage_id, days)

@st.cache_data(ttl=60)
def load_onboarding_status():
    res = supabase.table("v_onboarding_status").select("*").execute()
    return pd.DataFrame(res.data or [])

@st.cache_data(ttl=60)
def load_onboarding_logs(garage_id):
    q = supabase.table("onboarding_logs").select("*").order("created_at", desc=True).limit(100)
    if garage_id:
        q = q.eq("garage_id", garage_id)
    return pd.DataFrame(q.execute().data or [])


# ─── Helpers ──────────────────────────────────────────────────────────────────
def fmt_duration(s):
    if pd.isna(s):
        return "—"
    s = int(s)
    return f"{s // 60}m{s % 60:02d}s"

def to_paris(series):
    return pd.to_datetime(series, format="ISO8601", utc=True).dt.tz_convert("Europe/Paris")

def daily_counts(df, label):
    """Série journalière complète (jours sans activité inclus)."""
    d = df.copy()
    d["date"] = d["dt"].dt.tz_convert("Europe/Paris").dt.date
    out = d.groupby("date").size().reset_index(name=label)
    full = pd.date_range(out["date"].min(), out["date"].max(), freq="D").date
    return out.set_index("date").reindex(full, fill_value=0).rename_axis("date").reset_index()

def card(title, subtitle=""):
    """Ouvre une carte stylée ; à utiliser en context manager."""
    box = st.container(border=True)
    box.markdown(T.card_title(title, subtitle), unsafe_allow_html=True)
    return box

def show_empty(container, title, hint=""):
    container.markdown(T.empty_state(title, hint), unsafe_allow_html=True)

PLOT_CFG = {"displayModeBar": False}

def ranked_bar(labels, values, colors, hover_unit="appels"):
    """
    Barre horizontale triée : compare des catégories nommées.
    (Un donut serait illisible ici — trop de parts, valeurs proches.)
    Chaque barre porte son libellé ET sa valeur : l'identité ne repose pas sur la couleur.
    """
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=values, textposition="outside",
        textfont=dict(color=T.INK_DIM, size=11),
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x} " + hover_unit + "<extra></extra>",
    ))
    fig.update_layout(yaxis=dict(autorange="reversed"))
    fig.update_xaxes(visible=False)
    return fig


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div class="al-logo"><span class="al-logo-dot"></span>AgentLumy</div>'
        '<div class="al-logo-sub">Monitoring</div>',
        unsafe_allow_html=True,
    )

    garages_df = load_garages()
    garage_options = {"Tous les garages": None}
    if not garages_df.empty:
        for _, row in garages_df.iterrows():
            garage_options[f"{row['name']}"] = row["id"]

    # Les filtres sont lisibles/partageables via l'URL : ?garage=...&periode=...
    qp = st.query_params
    noms = list(garage_options.keys())
    idx_garage = noms.index(qp["garage"]) if qp.get("garage") in noms else 0
    selected_name = st.selectbox("Garage", noms, index=idx_garage)
    selected_id   = garage_options[selected_name]

    PERIODES = {"7 jours": 7, "30 jours": 30, "90 jours": 90,
                "1 an": 365, "Tout l'historique": None}
    libelles = list(PERIODES.keys())
    idx_periode = libelles.index(qp["periode"]) if qp.get("periode") in libelles else 1
    periode_label = st.selectbox("Période", libelles, index=idx_periode)
    days = PERIODES[periode_label]

    st.query_params.update({"garage": selected_name, "periode": periode_label})

    if st.button("Rafraîchir les données", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Mis à jour : {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # Statut d'onboarding : icône + libellé, jamais la couleur seule
    if not garages_df.empty:
        st.divider()
        st.caption("Statut d'onboarding")
        icon_map = {
            "completed": (T.ICONS["check"],   T.GOOD),
            "pending":   (T.ICONS["pending"], T.WARNING),
            "failed":    (T.ICONS["failed"],  T.CRITICAL),
        }
        rows = []
        for _, row in garages_df.iterrows():
            icon, color = icon_map.get(row.get("onboarding_status"),
                                       (T.ICONS["building"], T.MUTED))
            rows.append(
                f'<div class="al-garage-row"><span style="color:{color}">{icon}</span>'
                f'<span>{row["name"]}</span></div>'
            )
        st.markdown("".join(rows), unsafe_allow_html=True)


# ─── Chargement données ───────────────────────────────────────────────────────
calls_df  = load_calls(selected_id, days)
appts_df  = load_appointments(selected_id, days)
notifs_df = load_notifications(selected_id, days)

st.markdown(
    f'<div class="al-header"><h1>{selected_name}</h1>'
    f'<span class="al-scope">{periode_label.lower()}</span></div>',
    unsafe_allow_html=True,
)

tab1, tab2, tab3 = st.tabs(["Appels & KPIs", "Rendez-vous", "Onboarding"])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Appels & KPIs
# ═════════════════════════════════════════════════════════════════════════════
with tab1:
    total_calls = len(calls_df)
    rdv_pris = avg_dur = echecs = urgences = transferts = 0
    if not calls_df.empty:
        rdv_pris   = int((calls_df["call_status"] == "rdv_pris").sum())
        echecs     = int(calls_df["call_status"].isin(CALL_STATUS_ECHEC).sum())
        urgences   = int(calls_df["urgency_level"].isin(URGENCE_FORTE).sum())
        transferts = int(calls_df["transfer_triggered"].fillna(False).astype(bool).sum())
        avg_dur    = int(calls_df["duration_seconds"].dropna().mean() or 0)

    # Taux de conversion = appels qui aboutissent à un RDV / appels traités
    taux_conv = round(rdv_pris / total_calls * 100, 1) if total_calls else 0.0
    ecart     = taux_conv - OBJECTIF_CONVERSION

    st.markdown(T.tiles_row([
        T.stat_tile("phone", "Appels reçus", f"{total_calls}"),
        T.stat_tile("calendar", "RDV pris", f"{rdv_pris}"),
        T.stat_tile(
            "target", "Taux de conversion", f"{taux_conv}", unit="%",
            delta=f"{abs(ecart):.1f} pts vs objectif {OBJECTIF_CONVERSION:.0f}%",
            delta_dir="up" if ecart >= 0 else "down", lead=True,
        ),
        T.stat_tile("clock", "Durée moyenne", fmt_duration(avg_dur)),
        T.stat_tile(
            "missed", "Appels ratés", f"{echecs}",
            delta="abandon ou erreur technique" if echecs else "aucun",
            delta_dir="down" if echecs else "flat",
        ),
        T.stat_tile(
            "siren", "Urgences", f"{urgences}",
            delta=f"{transferts} transfert{'s' if transferts > 1 else ''} au patron",
            delta_dir="flat",
        ),
    ]), unsafe_allow_html=True)

    col_l, col_r = st.columns([1.15, 1], gap="small")

    # Volume dans le temps → barres verticales
    with col_l:
        box = card("Appels par jour", "volume quotidien sur la période")
        if not calls_df.empty:
            daily = daily_counts(calls_df, "appels")
            fig = go.Figure(go.Bar(
                x=daily["date"], y=daily["appels"],
                marker=dict(color=T.SERIES[0], line=dict(width=0)),
                hovertemplate="<b>%{x|%d/%m/%Y}</b><br>%{y} appels<extra></extra>",
            ))
            box.plotly_chart(T.style_fig(fig, height=250), width="stretch", config=PLOT_CFG)
        else:
            show_empty(box, "Aucun appel sur la période",
                       "Élargis la période dans le panneau de gauche.")

    # Comparaison de catégories nommées → barres horizontales triées
    with col_r:
        box = card("Issue des appels", "comment se terminent les conversations")
        if not calls_df.empty:
            counts = (calls_df["call_status"]
                      .map(lambda s: CALL_STATUS_LABELS.get(s, s or "Inconnu"))
                      .value_counts())
            # Au-delà de 6 classes les couleurs se brouillent : le reste va dans « Autres »
            if len(counts) > 6:
                autres = counts[6:].sum()
                counts = counts[:6]
                counts["Autres"] = autres
            colors = [T.SERIES[i % len(T.SERIES)] for i in range(len(counts))]
            fig2 = ranked_bar(list(counts.index), list(counts.values), colors)
            box.plotly_chart(T.style_fig(fig2, height=250), width="stretch", config=PLOT_CFG)
        else:
            show_empty(box, "Aucune donnée de statut")

    # Nature des demandes
    if not calls_df.empty and calls_df["demand_type"].notna().any():
        box = card("Nature des demandes", "ce que les clients appellent demander")
        dem = (calls_df["demand_type"].fillna("non qualifié")
               .str.replace("_", " ").str.capitalize()
               .value_counts())
        fig_d = ranked_bar(list(dem.index), list(dem.values),
                           [T.SERIES[2]] * len(dem))
        box.plotly_chart(T.style_fig(fig_d, height=max(150, 34 * len(dem))),
                         width="stretch", config=PLOT_CFG)

    # Journal des appels
    box = card("Derniers appels", "25 plus récents")
    if not calls_df.empty:
        disp = pd.DataFrame({
            "Date":     calls_df["dt"].dt.tz_convert("Europe/Paris").dt.strftime("%d/%m %H:%M"),
            "Appelant": calls_df["caller_phone"],
            "Demande":  calls_df["demand_type"].fillna("—").str.replace("_", " "),
            "Issue":    calls_df["call_status"].map(lambda s: CALL_STATUS_LABELS.get(s, s or "—")),
            "Urgence":  calls_df["urgency_level"].fillna("—"),
            "Durée":    calls_df["duration_seconds"].apply(fmt_duration),
            "Résumé":   calls_df["summary"].fillna(""),
        }).head(25)
        box.dataframe(disp, width="stretch", hide_index=True)
    else:
        show_empty(box, "Aucun appel enregistré sur la période")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Rendez-vous
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    statuts = pd.Series(dtype=str)
    if not appts_df.empty:
        statuts    = appts_df["status"].map(lambda s: APPT_STATUS_LABELS.get(s, s or "—"))
        annules    = int(appts_df["status"].isin(["annule", "no_show"]).sum())
        a_venir    = int((pd.to_datetime(appts_df["scheduled_at"], format="ISO8601", utc=True)
                          > datetime.now(timezone.utc)).sum())
        taux_annul = round(annules / len(appts_df) * 100, 1)

        st.markdown(T.tiles_row([
            T.stat_tile("calendar", "RDV créés", f"{len(appts_df)}"),
            T.stat_tile("upcoming", "À venir", f"{a_venir}"),
            T.stat_tile("cancel", "Annulés / no-show", f"{annules}"),
            T.stat_tile(
                "trend", "Taux d'annulation", f"{taux_annul}", unit="%",
                delta="part des RDV perdus",
                delta_dir="down" if taux_annul > 0 else "flat",
            ),
        ]), unsafe_allow_html=True)

    col_l, col_r = st.columns(2, gap="small")

    with col_l:
        box = card("Statut des rendez-vous", "état actuel du carnet")
        if not appts_df.empty:
            vc     = statuts.value_counts()
            colors = [APPT_STATUS_COLORS.get(s, T.MUTED) for s in vc.index]
            fig3   = ranked_bar(list(vc.index), list(vc.values), colors, hover_unit="RDV")
            box.plotly_chart(T.style_fig(fig3, height=230), width="stretch", config=PLOT_CFG)
        else:
            show_empty(box, "Aucun rendez-vous")

    with col_r:
        box = card("RDV pris par jour", "rythme de prise de rendez-vous")
        if not appts_df.empty:
            daily_a = daily_counts(appts_df, "rdv")
            fig4 = go.Figure(go.Scatter(
                x=daily_a["date"], y=daily_a["rdv"],
                mode="lines+markers",
                line=dict(color=T.SERIES[1], width=2),
                marker=dict(size=8, color=T.SERIES[1],
                            line=dict(width=2, color=T.SURFACE)),
                hovertemplate="<b>%{x|%d/%m/%Y}</b><br>%{y} RDV<extra></extra>",
            ))
            fig4.update_layout(hovermode="x unified")
            box.plotly_chart(T.style_fig(fig4, height=230), width="stretch", config=PLOT_CFG)
        else:
            show_empty(box, "Aucun rendez-vous")

    box = card("Liste des rendez-vous", "30 plus récents")
    if not appts_df.empty:
        disp_a = pd.DataFrame({
            "Créé le":    appts_df["dt"].dt.tz_convert("Europe/Paris").dt.strftime("%d/%m %H:%M"),
            "Prévu le":   to_paris(appts_df["scheduled_at"]).dt.strftime("%d/%m/%Y %H:%M"),
            "Prestation": appts_df["title"].fillna("—"),
            "Client":     appts_df["client_name"].fillna("—"),
            "Téléphone":  appts_df["client_phone"].fillna("—"),
            "Durée":      appts_df["duration_minutes"].fillna(0).astype(int).astype(str) + " min",
            "Statut":     statuts,
        }).head(30)
        box.dataframe(disp_a, width="stretch", hide_index=True)
    else:
        show_empty(box, "Aucun rendez-vous enregistré")

    box = card("Notifications envoyées", "SMS et emails sortants")
    if not notifs_df.empty:
        box.markdown(T.tiles_row([
            T.stat_tile("sms",   "SMS",    f"{int((notifs_df['channel'] == 'sms').sum())}"),
            T.stat_tile("mail",  "Emails", f"{int((notifs_df['channel'] == 'email').sum())}"),
            T.stat_tile("alert", "Échecs", f"{int((notifs_df['status'] == 'failed').sum())}"),
        ]), unsafe_allow_html=True)

        disp_n = pd.DataFrame({
            "Date":         to_paris(notifs_df["created_at"]).dt.strftime("%d/%m %H:%M"),
            "Canal":        notifs_df["channel"],
            "Destinataire": notifs_df["recipient_phone"].fillna(
                                notifs_df["recipient_email"]).fillna("—"),
            "Statut":       notifs_df["status"],
            "Erreur":       notifs_df["error_message"].fillna(""),
        }).head(20)
        box.dataframe(disp_n, width="stretch", hide_index=True)
    else:
        show_empty(box, "Aucune notification sur la période",
                   "Chaque SMS ou email envoyé par l'agent apparaîtra ici.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — Onboarding
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    ob_df = load_onboarding_status()

    if not ob_df.empty:
        vc = ob_df["onboarding_status"].value_counts()
        st.markdown(T.tiles_row([
            T.stat_tile("check",    "Complétés",  f"{int(vc.get('completed', 0))}"),
            T.stat_tile("pending",  "En attente", f"{int(vc.get('pending', 0))}"),
            T.stat_tile("failed",   "Échoués",    f"{int(vc.get('failed', 0))}",
                        delta="à reprendre" if vc.get("failed", 0) else "aucun",
                        delta_dir="down" if vc.get("failed", 0) else "flat"),
            T.stat_tile("building", "Garages",    f"{len(ob_df)}"),
        ]), unsafe_allow_html=True)

        box = card("Statut par garage", "état de la mise en service")
        disp_ob = pd.DataFrame({
            "Garage":         ob_df["name"],
            "Statut":         ob_df["onboarding_status"],
            "N° agent":       ob_df["twilio_phone_number"].fillna("—"),
            "Assistant Vapi": ob_df["vapi_assistant_id"].fillna("—"),
            "Cal.com":        ob_df["calcom_username"].fillna("—"),
            "Dernière étape": ob_df["last_step"].fillna("—"),
            "Erreur":         ob_df["onboarding_error"].fillna(""),
        })
        box.dataframe(disp_ob, width="stretch", hide_index=True)
    else:
        show_empty(st.container(border=True), "Vue v_onboarding_status vide ou inaccessible")

    logs_df = load_onboarding_logs(selected_id)

    if not logs_df.empty:
        box = card("Fiabilité des étapes", "quelle étape bloque la mise en service")
        recap = (logs_df.groupby(["step", "status"]).size()
                 .reset_index(name="count"))
        # Part-to-whole par étape → barres empilées + légende (2 séries)
        fig_s = px.bar(
            recap, x="step", y="count", color="status", barmode="stack",
            color_discrete_map={"success": T.GOOD, "failed": T.CRITICAL},
            labels={"step": "", "count": "Exécutions", "status": ""},
        )
        fig_s.update_traces(marker_line=dict(width=2, color=T.SURFACE),
                            hovertemplate="<b>%{x}</b><br>%{y} — %{fullData.name}<extra></extra>")
        box.plotly_chart(T.style_fig(fig_s, height=270, showlegend=True),
                         width="stretch", config=PLOT_CFG)

        box = card("Journal d'onboarding", "50 événements les plus récents")
        disp_l = pd.DataFrame({
            "Date":   to_paris(logs_df["created_at"]).dt.strftime("%d/%m %H:%M:%S"),
            "Étape":  logs_df["step"],
            "Statut": logs_df["status"],
            "Durée":  logs_df["duration_ms"].fillna(0).astype(int).astype(str) + " ms",
            "Erreur": logs_df["error_message"].fillna(""),
        }).head(50)

        def color_status(val):
            return {"success": f"color:{T.GOOD};",
                    "failed":  f"color:{T.CRITICAL};",
                    "pending": f"color:{T.WARNING};"}.get(str(val), "")

        box.dataframe(disp_l.style.map(color_status, subset=["Statut"]),
                      width="stretch", hide_index=True)
    else:
        show_empty(st.container(border=True), "Aucun log d'onboarding")
