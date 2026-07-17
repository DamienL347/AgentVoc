# ─────────────────────────────────────────────────────────────────────────────
# AgentLumy — Dashboard de monitoring
# Lancer : streamlit run dashboard.py
# ─────────────────────────────────────────────────────────────────────────────

import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AgentLumy — Dashboard",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 2rem; }
[data-testid="stMetricLabel"] { font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

# ─── Connexion Supabase ───────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    # Service role key pour bypasser RLS et tout lire
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        st.error("❌ SUPABASE_URL ou SUPABASE_SERVICE_KEY manquants dans .env")
        st.stop()
    return create_client(url, key)

supabase = get_supabase()

# ─── Loaders (cache 60s) ──────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_garages():
    res = supabase.table("garages") \
        .select("id, name, garage_type, onboarding_status, twilio_phone_number, created_at") \
        .execute()
    return pd.DataFrame(res.data or [])

@st.cache_data(ttl=60)
def load_calls(garage_id, days):
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    q = supabase.table("calls").select("*").gte("created_at", since).order("created_at", desc=True)
    if garage_id:
        q = q.eq("garage_id", garage_id)
    return pd.DataFrame(q.execute().data or [])

@st.cache_data(ttl=60)
def load_appointments(garage_id, days):
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    q = supabase.table("appointments").select("*").gte("created_at", since)
    if garage_id:
        q = q.eq("garage_id", garage_id)
    return pd.DataFrame(q.execute().data or [])

@st.cache_data(ttl=60)
def load_notifications(garage_id, days):
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    q = supabase.table("notifications").select("*").gte("created_at", since)
    if garage_id:
        q = q.eq("garage_id", garage_id)
    return pd.DataFrame(q.execute().data or [])

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

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🚗 AgentLumy")
    st.caption("Dashboard de monitoring")
    st.divider()

    garages_df = load_garages()
    garage_options = {"Tous les garages": None}
    if not garages_df.empty:
        for _, row in garages_df.iterrows():
            garage_options[f"{row['name']}"] = row["id"]

    selected_name = st.selectbox("Garage", list(garage_options.keys()))
    selected_id   = garage_options[selected_name]

    days = st.slider("Période (jours)", min_value=7, max_value=90, value=30, step=7)
    st.divider()

    if st.button("🔄 Rafraîchir les données", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Mis à jour : {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # Statut garages mini-table
    if not garages_df.empty:
        st.divider()
        st.caption("Statut des garages")
        for _, row in garages_df.iterrows():
            icon = "✅" if row.get("onboarding_status") == "completed" else "⏳"
            st.caption(f"{icon} {row['name']}")

# ─── Chargement données ───────────────────────────────────────────────────────
calls_df = load_calls(selected_id, days)
appts_df = load_appointments(selected_id, days)
notifs_df = load_notifications(selected_id, days)

# ─── Titre principal ──────────────────────────────────────────────────────────
titre = f"**{selected_name}** — {days} derniers jours"
st.markdown(f"## {titre}")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📊 Appels & KPIs", "📅 Rendez-vous", "🏗️ Onboarding"])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Appels & KPIs
# ═════════════════════════════════════════════════════════════════════════════
with tab1:

    # KPIs ────────────────────────────────────────────────────────────────────
    total_calls = len(calls_df)
    total_appts = len(appts_df)
    taux_conv   = round(total_appts / total_calls * 100, 1) if total_calls > 0 else 0

    avg_dur = 0
    missed  = 0
    if not calls_df.empty:
        if "duration_seconds" in calls_df.columns:
            avg_dur = int(calls_df["duration_seconds"].dropna().mean() or 0)
        if "status" in calls_df.columns:
            missed = int((calls_df["status"] == "missed").sum())

    total_sms    = len(notifs_df[notifs_df["type"] == "sms"])   if not notifs_df.empty and "type" in notifs_df.columns else 0
    total_emails = len(notifs_df[notifs_df["type"] == "email"]) if not notifs_df.empty and "type" in notifs_df.columns else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("📞 Appels",         total_calls)
    c2.metric("📅 RDV pris",       total_appts)
    c3.metric("🎯 Taux conversion", f"{taux_conv}%",
              delta=f"{taux_conv - 30:.1f}% vs objectif 30%")
    c4.metric("⏱️ Durée moyenne",   f"{avg_dur}s")
    c5.metric("📵 Manqués",         missed,
              delta=f"-{missed}" if missed > 0 else None,
              delta_color="inverse")
    c6.metric("✉️ SMS / Emails",    f"{total_sms} / {total_emails}")

    st.divider()

    # Graphiques ──────────────────────────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Appels par jour")
        if not calls_df.empty and "created_at" in calls_df.columns:
            calls_df["date"] = pd.to_datetime(calls_df["created_at"]).dt.date
            daily = calls_df.groupby("date").size().reset_index(name="appels")
            fig = px.bar(daily, x="date", y="appels",
                         color_discrete_sequence=["#7c3aed"],
                         labels={"date": "", "appels": "Appels"})
            fig.update_layout(margin=dict(l=0,r=0,t=10,b=0),
                              plot_bgcolor="rgba(0,0,0,0)",
                              paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucun appel sur la période")

    with col_r:
        st.subheader("Statut des appels")
        if not calls_df.empty and "status" in calls_df.columns:
            status_ct = calls_df["status"].value_counts().reset_index()
            status_ct.columns = ["statut", "count"]
            fig2 = px.pie(status_ct, names="statut", values="count",
                          color_discrete_sequence=px.colors.qualitative.Pastel,
                          hole=0.4)
            fig2.update_layout(margin=dict(l=0,r=0,t=10,b=0),
                               paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Aucune donnée de statut")

    # Table derniers appels ───────────────────────────────────────────────────
    st.subheader("Derniers appels")
    if not calls_df.empty:
        cols = [c for c in ["created_at","caller_phone","status","duration_seconds","garage_id"] if c in calls_df.columns]
        disp = calls_df[cols].head(25).copy()
        if "created_at" in disp.columns:
            disp["created_at"] = pd.to_datetime(disp["created_at"]).dt.strftime("%d/%m %H:%M")
        if "duration_seconds" in disp.columns:
            disp["duration_seconds"] = disp["duration_seconds"].apply(
                lambda s: f"{int(s//60)}m{int(s%60):02d}s" if pd.notna(s) else "-"
            )
        disp.columns = [c.replace("_", " ").title() for c in disp.columns]
        st.dataframe(disp, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun appel enregistré sur la période")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Rendez-vous
# ═════════════════════════════════════════════════════════════════════════════
with tab2:

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Statut des RDV")
        if not appts_df.empty and "status" in appts_df.columns:
            color_map = {
                "confirmed": "#22c55e", "completed": "#3b82f6",
                "cancelled": "#ef4444", "pending":   "#f59e0b",
            }
            appt_status = appts_df["status"].value_counts().reset_index()
            appt_status.columns = ["statut", "count"]
            fig3 = px.bar(appt_status, x="statut", y="count",
                          color="statut", color_discrete_map=color_map,
                          labels={"statut": "", "count": "RDV"})
            fig3.update_layout(showlegend=False, margin=dict(l=0,r=0,t=10,b=0),
                               plot_bgcolor="rgba(0,0,0,0)",
                               paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Aucun rendez-vous")

    with col_r:
        st.subheader("RDV par jour")
        if not appts_df.empty and "created_at" in appts_df.columns:
            appts_df["date"] = pd.to_datetime(appts_df["created_at"]).dt.date
            daily_a = appts_df.groupby("date").size().reset_index(name="rdv")
            fig4 = px.line(daily_a, x="date", y="rdv", markers=True,
                           color_discrete_sequence=["#06b6d4"],
                           labels={"date": "", "rdv": "RDV"})
            fig4.update_layout(margin=dict(l=0,r=0,t=10,b=0),
                               plot_bgcolor="rgba(0,0,0,0)",
                               paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("Aucun rendez-vous")

    st.subheader("Liste des rendez-vous")
    if not appts_df.empty:
        cols = [c for c in ["created_at","status","service_type","scheduled_at","garage_id"] if c in appts_df.columns]
        disp_a = appts_df[cols].head(30).copy()
        for col in ["created_at", "scheduled_at"]:
            if col in disp_a.columns:
                disp_a[col] = pd.to_datetime(disp_a[col]).dt.strftime("%d/%m %H:%M")
        disp_a.columns = [c.replace("_", " ").title() for c in disp_a.columns]
        st.dataframe(disp_a, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun rendez-vous enregistré")

    # Notifications
    st.subheader("Notifications envoyées")
    if not notifs_df.empty:
        cols_n = [c for c in ["created_at","type","status","garage_id"] if c in notifs_df.columns]
        disp_n = notifs_df[cols_n].head(20).copy()
        if "created_at" in disp_n.columns:
            disp_n["created_at"] = pd.to_datetime(disp_n["created_at"]).dt.strftime("%d/%m %H:%M")
        disp_n.columns = [c.replace("_", " ").title() for c in disp_n.columns]
        st.dataframe(disp_n, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune notification")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — Onboarding
# ═════════════════════════════════════════════════════════════════════════════
with tab3:

    ob_df = load_onboarding_status()

    if not ob_df.empty:
        # KPIs onboarding
        if "onboarding_status" in ob_df.columns:
            vc = ob_df["onboarding_status"].value_counts()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("✅ Complétés",  vc.get("completed",  0))
            c2.metric("⏳ En cours",   vc.get("in_progress", 0))
            c3.metric("❌ Échoués",    vc.get("failed",      0))
            c4.metric("🏢 Total",      len(ob_df))
            st.divider()

        st.subheader("Statut par garage")
        st.dataframe(ob_df, use_container_width=True, hide_index=True)
    else:
        st.info("Vue v_onboarding_status vide ou non accessible")

    st.subheader("Logs d'onboarding")
    logs_df = load_onboarding_logs(selected_id)
    if not logs_df.empty:
        cols_l = [c for c in ["created_at","garage_id","step_number","step_name","status","error_message"] if c in logs_df.columns]
        disp_l = logs_df[cols_l].head(50).copy()
        if "created_at" in disp_l.columns:
            disp_l["created_at"] = pd.to_datetime(disp_l["created_at"]).dt.strftime("%d/%m %H:%M")
        # Coloriser les statuts
        def color_status(val):
            colors = {"success": "background-color: #16a34a22", "failed": "background-color: #dc262622", "pending": "background-color: #d9770622"}
            return colors.get(str(val), "")
        if "status" in disp_l.columns:
            st.dataframe(disp_l.style.applymap(color_status, subset=["status"]),
                         use_container_width=True, hide_index=True)
        else:
            st.dataframe(disp_l, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun log d'onboarding")