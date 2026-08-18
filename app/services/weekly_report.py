"""
Rapport hebdomadaire adressé au garage client.

Objectif commercial : rappeler chaque semaine ce que l'agent a rapporté. Un
dashboard est *pull* — il faut que le garagiste pense à s'y connecter, et il ne
le fera pas, il a les mains dans un moteur. Un email est *push* : il le reçoit,
donc il le lit. C'est aussi un point de contact récurrent qui rend la
reconduction naturelle.

Le chiffre mis en avant est **les appels pris hors horaires** : ce sont les
clients que le garage aurait perdus sans l'agent. Le taux de conversion ou la
durée moyenne intéressent l'exploitant du service, pas le garagiste.

Le rendu s'appuie sur `app/templates/emails/rapport_hebdomadaire.{html,txt}` —
mêmes variables `{{...}}` que les prompts, pour n'avoir qu'un seul mécanisme de
gabarit dans le projet.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")
TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "emails"

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]

# Signataire par défaut : le rapport est envoyé au nom d'une personne, pas d'un
# robot. Un garagiste répond à quelqu'un, pas à « l'équipe ».
AUTEUR_DEFAUT = {
    "AUTEUR_NOM":   "Damien Lauger",
    "AUTEUR_ROLE":  "Votre interlocuteur AgentLumy",
    "AUTEUR_EMAIL": "rdv@agentlumy.com",
    "AUTEUR_TEL":   "",          # à renseigner dans .env (REPORT_AUTHOR_PHONE)
}

LIBELLES_DEMANDES = {
    "prise_rdv":            "Prise de rendez-vous",
    "information":          "Demande d'information",
    "devis":                "Demande de devis",
    "modification_rdv":     "Modification de rendez-vous",
    "annulation_rdv":       "Annulation",
    "depannage_urgent":     "Dépannage urgent",
    "depannage_non_urgent": "Dépannage",
    "reclamation":          "Réclamation",
    "autre":                "Autre",
}


def _date_fr(dt: datetime) -> str:
    dt = dt.astimezone(PARIS_TZ)
    return f"{dt.day} {MOIS_FR[dt.month - 1]}"


def _duree_fr(secondes: Optional[float]) -> str:
    if not secondes:
        return "—"
    secondes = int(secondes)
    return f"{secondes // 60} min {secondes % 60:02d} s" if secondes >= 60 \
        else f"{secondes} secondes"


class WeeklyReport:
    """Calcule les indicateurs de la semaine et produit l'email."""

    def __init__(self):
        self.db = None

    def _lazy_init(self):
        if self.db is None:
            from app.db.supabase_client import get_supabase_client
            self.db = get_supabase_client()

    # ── Indicateurs ──────────────────────────────────────────────────────────

    def collecter(self, garage_id: str, *, jusqu_a: Optional[datetime] = None,
                  jours: int = 7) -> dict:
        """Indicateurs de la période pour un garage."""
        from app.utils.business_hours import is_open_at

        self._lazy_init()
        fin    = (jusqu_a or datetime.now(timezone.utc)).astimezone(timezone.utc)
        debut  = fin - timedelta(days=jours)

        garage = (self.db.table("garages")
                  .select("name, email, business_hours")
                  .eq("id", str(garage_id)).single().execute()).data or {}

        appels = (self.db.table("calls")
                  .select("call_status, demand_type, urgency_level, "
                          "duration_seconds, started_at, created_at, transfer_triggered")
                  .eq("garage_id", str(garage_id))
                  .gte("created_at", debut.isoformat())
                  .lte("created_at", fin.isoformat())
                  .execute()).data or []

        rdv = (self.db.table("appointments")
               .select("id")
               .eq("garage_id", str(garage_id))
               .gte("created_at", debut.isoformat())
               .lte("created_at", fin.isoformat())
               .execute()).data or []

        horaires = garage.get("business_hours")
        hors_horaires = 0
        for appel in appels:
            quand = appel.get("started_at") or appel.get("created_at")
            try:
                moment = datetime.fromisoformat(str(quand).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            # « Hors horaires » = l'appel serait tombé dans le vide sans l'agent.
            if not is_open_at(horaires, moment):
                hors_horaires += 1

        durees = [a["duration_seconds"] for a in appels if a.get("duration_seconds")]
        demandes: dict[str, int] = {}
        for appel in appels:
            demandes[appel.get("demand_type") or "autre"] = \
                demandes.get(appel.get("demand_type") or "autre", 0) + 1

        return {
            "garage_nom":     garage.get("name", "votre garage"),
            "garage_email":   garage.get("email"),
            "debut":          debut,
            "fin":            fin,
            "appels_total":   len(appels),
            "hors_horaires":  hors_horaires,
            "rdv_pris":       len(rdv),
            "urgences":       sum(1 for a in appels
                                  if a.get("urgency_level") in ("elevee", "critique")),
            "messages":       sum(1 for a in appels
                                  if a.get("call_status") == "message_laisse"),
            "transferts":     sum(1 for a in appels if a.get("transfer_triggered")),
            "duree_moyenne":  sum(durees) / len(durees) if durees else 0,
            "demandes":       demandes,
        }

    # ── Rédaction ────────────────────────────────────────────────────────────

    def _phrase_cle(self, k: dict) -> str:
        """
        La phrase qui donne du sens au chiffre. Adaptée au volume : féliciter
        pour « 0 appel » sonnerait faux, et un rapport qui sonne faux ne se lit
        plus.
        """
        hors, rdv = k["hors_horaires"], k["rdv_pris"]

        if k["appels_total"] == 0:
            return ("Aucun appel cette semaine sur votre ligne Lumy. "
                    "Si cela vous surprend, dites-le moi : je vérifie le renvoi d'appel.")
        if hors == 0:
            return (f"Tous les appels sont arrivés pendant vos heures d'ouverture. "
                    f"Lumy a traité {k['appels_total']} appel(s) sans vous interrompre.")

        socle = ("Autant d'appels qui auraient sonné dans le vide — le soir, "
                 "le week-end ou pendant que vous étiez sous un capot.")
        if rdv:
            # Formulation prudente : `rdv` porte sur TOUS les appels de la
            # semaine, pas seulement sur ceux hors horaires. Écrire « dont X »
            # produirait des phrases fausses (« 9 appels, dont 11 rendez-vous »)
            # et un rapport qui se contredit ne convainc personne.
            return socle + (f" Sur l'ensemble de la semaine, {rdv} rendez-vous "
                            f"ont été pris automatiquement.")
        return socle

    def _top_demandes_html(self, demandes: dict, total: int) -> str:
        if not demandes:
            return ('<tr><td style="padding:6px 0; color:#6b7280;">'
                    'Aucune demande enregistrée cette semaine.</td></tr>')

        lignes = []
        for cle, nombre in sorted(demandes.items(), key=lambda x: -x[1])[:5]:
            libelle = LIBELLES_DEMANDES.get(cle, "Autre")
            part    = round(nombre / total * 100) if total else 0
            lignes.append(
                f'<tr>'
                f'<td style="padding:7px 0; border-bottom:1px solid #f3f4f6;">{libelle}</td>'
                f'<td align="right" style="padding:7px 0; border-bottom:1px solid #f3f4f6; '
                f'color:#101214; font-weight:600;">{nombre}<span style="color:#9ca3af; '
                f'font-weight:400;"> ({part} %)</span></td>'
                f'</tr>'
            )
        return "".join(lignes)

    def _top_demandes_texte(self, demandes: dict, total: int) -> str:
        if not demandes:
            return "  Aucune demande enregistree cette semaine."
        lignes = []
        for cle, nombre in sorted(demandes.items(), key=lambda x: -x[1])[:5]:
            libelle = LIBELLES_DEMANDES.get(cle, "Autre")
            part    = round(nombre / total * 100) if total else 0
            lignes.append(f"  {libelle:24} {nombre} ({part} %)")
        return "\n".join(lignes)

    def _point_attention(self, k: dict) -> tuple[str, str]:
        """
        Signale ce qui mérite une action du garage. Rien à dire = bloc vide :
        une alerte inventée chaque semaine perd tout pouvoir d'alerte.
        """
        if k["urgences"]:
            texte = (f"{k['urgences']} appel(s) urgent(s) ont été transmis. "
                     f"Vérifiez qu'ils ont bien été rappelés.")
        elif k["messages"]:
            texte = (f"{k['messages']} message(s) attendent un rappel de votre part.")
        else:
            return "", ""

        html = (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="background-color:#fef2f2; border-radius:6px;">'
            '<tr><td style="padding:14px 18px; font-size:14px; color:#991b1b;">'
            f'<strong>À vérifier —</strong> {texte}'
            '</td></tr></table>'
        )
        return html, f"A VERIFIER : {texte}"

    # ── Rendu ────────────────────────────────────────────────────────────────

    def rendre(self, kpis: dict, auteur: Optional[dict] = None) -> dict:
        """Retourne {'sujet', 'html', 'texte'} prêts à envoyer."""
        signataire = {**AUTEUR_DEFAUT, **(auteur or {})}
        initiales  = "".join(m[0] for m in signataire["AUTEUR_NOM"].split()[:2]).upper()

        attention_html, attention_texte = self._point_attention(kpis)

        variables = {
            **signataire,
            "AUTEUR_INITIALES":     initiales,
            "GARAGE_NAME":          kpis["garage_nom"],
            "PERIODE_DEBUT":        _date_fr(kpis["debut"]),
            "PERIODE_FIN":          _date_fr(kpis["fin"]),
            "APPELS_TOTAL":         str(kpis["appels_total"]),
            "APPELS_HORS_HORAIRES": str(kpis["hors_horaires"]),
            "RDV_PRIS":             str(kpis["rdv_pris"]),
            "URGENCES":             str(kpis["urgences"]),
            "MESSAGES_PRIS":        str(kpis["messages"]),
            "DUREE_MOYENNE":        _duree_fr(kpis["duree_moyenne"]),
            "PHRASE_CLE":           self._phrase_cle(kpis),
            "TOP_DEMANDES":         self._top_demandes_html(kpis["demandes"],
                                                            kpis["appels_total"]),
            "TOP_DEMANDES_TEXTE":   self._top_demandes_texte(kpis["demandes"],
                                                             kpis["appels_total"]),
            "POINT_ATTENTION":       attention_html,
            "POINT_ATTENTION_TEXTE": attention_texte,
            "LIEN_PREFERENCES":     "mailto:rdv@agentlumy.com?subject=Rapports%20hebdomadaires",
        }

        html  = (TEMPLATES / "rapport_hebdomadaire.html").read_text(encoding="utf-8")
        texte = (TEMPLATES / "rapport_hebdomadaire.txt").read_text(encoding="utf-8")
        # La version texte porte un mode d'emploi en tête : il ne part pas au client.
        texte = texte.split("--- couper ici", 1)[-1].split("\n", 1)[-1] \
            if "--- couper ici" in texte else texte

        for cle, valeur in variables.items():
            html  = html.replace(f"{{{{{cle}}}}}", str(valeur))
            texte = texte.replace(f"{{{{{cle}}}}}", str(valeur))

        restantes = [c for c in variables if f"{{{{{c}}}}}" in html]
        if restantes:
            logger.warning(f"⚠️ Variables non remplacées dans le rapport : {restantes}")

        sujet = (f"Votre semaine avec Lumy — {kpis['hors_horaires']} appel(s) "
                 f"pris pendant votre fermeture") if kpis["hors_horaires"] else \
                f"Votre semaine avec Lumy — {kpis['garage_nom']}"

        return {"sujet": sujet, "html": html, "texte": texte}

    # ── Envoi ────────────────────────────────────────────────────────────────

    async def envoyer(self, garage_id: str, *, destinataire: Optional[str] = None,
                      auteur: Optional[dict] = None, dry_run: bool = False) -> dict:
        kpis   = self.collecter(garage_id)
        rendu  = self.rendre(kpis, auteur)
        cible  = destinataire or kpis.get("garage_email")

        if not cible:
            return {"envoye": False, "raison": "aucune adresse email pour ce garage"}
        if dry_run:
            return {"envoye": False, "dry_run": True, "sujet": rendu["sujet"],
                    "destinataire": cible, "kpis": kpis}

        from app.integrations.resend_email import resend_client
        resultat = await resend_client.send_email(
            to=cible, subject=rendu["sujet"], html=rendu["html"], text=rendu["texte"],
        )
        return {"envoye": bool(resultat), "destinataire": cible,
                "sujet": rendu["sujet"], "erreur": resultat.error}


weekly_report = WeeklyReport()
