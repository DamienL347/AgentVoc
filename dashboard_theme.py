"""
Thème du dashboard AgentLumy — tokens, CSS et composants visuels.

Palette alignée sur la charte du site vitrine (portfolio/site/index.html) :
carbone + ambre. Les couleurs de SÉRIES ne sont pas les couleurs de marque :
elles sont issues d'une palette validée (bande de luminosité, plancher de
chroma, séparation daltonisme ΔE, contraste sur la surface sombre) —
voir scripts/validate_palette.js du skill dataviz.

    Palette de séries retenue (ordre = mécanisme de sécurité CVD, ne pas permuter) :
    #c98500 ambre · #199e70 vert · #3987e5 bleu · #d55181 magenta · #9085e9 violet · #e66767 rouge
    → ALL CHECKS PASS sur surface #14171d
"""

# ── Tokens ───────────────────────────────────────────────────────────────────

PLANE   = "#0b0d11"   # fond de page
SURFACE = "#14171d"   # fond des cartes (surface de rendu des graphiques)
LINE    = "#23272f"   # bordures / grille
INK     = "#f2efe8"   # texte principal (charte)
INK_DIM = "#9aa3ad"   # texte secondaire (charte)
MUTED   = "#7d858f"   # axes, libellés discrets
AMBER   = "#ffb300"   # accent de marque — UI uniquement, jamais une série

# Séries catégorielles (ordre validé — ne pas réordonner sans re-valider)
SERIES = ["#c98500", "#199e70", "#3987e5", "#d55181", "#9085e9", "#e66767"]

# Statuts — réservés, jamais réutilisés comme couleur de série
GOOD     = "#0ca30c"
WARNING  = "#fab219"
SERIOUS  = "#ec835a"
CRITICAL = "#d03b3b"


# ── Icônes (Lucide, tracé inline — pas d'emoji comme icône) ──────────────────

_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">{}</svg>'
)

ICONS = {
    "phone":     _ICON.format('<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/>'),
    "calendar":  _ICON.format('<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18M8 2v4M16 2v4"/><path d="m9 16 2 2 4-4"/>'),
    "target":    _ICON.format('<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>'),
    "clock":     _ICON.format('<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
    "missed":    _ICON.format('<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/><line x1="23" y1="1" x2="17" y2="7"/><line x1="17" y1="1" x2="23" y2="7"/>'),
    "siren":     _ICON.format('<path d="M7 18v-6a5 5 0 1 1 10 0v6"/><path d="M5 21a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-1a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2z"/><path d="M21 12h1M18.5 4.5 18 5M2 12h1M12 2v1M4.929 4.929l.707.707"/>'),
    "forward":   _ICON.format('<polyline points="15 17 20 12 15 7"/><path d="M4 18v-2a4 4 0 0 1 4-4h12"/>'),
    "upcoming":  _ICON.format('<path d="M12 8v4l3 3"/><circle cx="12" cy="12" r="10"/>'),
    "cancel":    _ICON.format('<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>'),
    "trend":     _ICON.format('<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>'),
    "check":     _ICON.format('<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'),
    "pending":   _ICON.format('<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>'),
    "failed":    _ICON.format('<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>'),
    "building":  _ICON.format('<rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M8 10h.01M16 10h.01M8 14h.01M16 14h.01"/>'),
    "sms":       _ICON.format('<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'),
    "mail":      _ICON.format('<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>'),
    "alert":     _ICON.format('<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
    "empty":     _ICON.format('<path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>'),
}

# Flèches de tendance : l'icône double le signe, la couleur ne porte jamais seule
_ARROW_UP   = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 7-7 7 7M12 19V5"/></svg>'
_ARROW_DOWN = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m19 12-7 7-7-7M12 5v14"/></svg>'


# ── CSS global ───────────────────────────────────────────────────────────────

CSS = f"""
<style>
  :root {{
    --plane:{PLANE}; --surface:{SURFACE}; --line:{LINE};
    --ink:{INK}; --ink-dim:{INK_DIM}; --muted:{MUTED}; --amber:{AMBER};
    --good:{GOOD}; --warning:{WARNING}; --critical:{CRITICAL};
    /* densité 8/10 : échelle 8→32px */
    --s1:8px; --s2:12px; --s3:16px; --s4:24px; --s5:32px;
  }}

  .stApp {{ background:var(--plane); }}
  .block-container {{ padding-top:var(--s4) !important; max-width:1500px; }}

  /* ── Barre de titre ─────────────────────────────────────────────── */
  .al-header {{
    display:flex; align-items:baseline; gap:var(--s2); flex-wrap:wrap;
    margin-bottom:var(--s3);
  }}
  .al-header h1 {{
    font-size:1.45rem; font-weight:650; color:var(--ink);
    margin:0; letter-spacing:-.01em;
  }}
  .al-header .al-scope {{
    font-size:.82rem; color:var(--ink-dim);
    border-left:1px solid var(--line); padding-left:var(--s2);
  }}

  /* ── Tuiles KPI ─────────────────────────────────────────────────── */
  .al-tiles {{
    display:grid; grid-template-columns:repeat(auto-fit,minmax(178px,1fr));
    gap:var(--s2); margin-bottom:var(--s4);
  }}
  .al-tile {{
    background:var(--surface); border:1px solid var(--line);
    border-radius:10px; padding:var(--s3);
    transition:border-color .18s ease, transform .18s ease;
  }}
  .al-tile:hover {{ border-color:#333944; transform:translateY(-1px); }}
  .al-tile-head {{
    display:flex; align-items:center; gap:var(--s1);
    color:var(--muted); font-size:.72rem; font-weight:600;
    text-transform:uppercase; letter-spacing:.06em; margin-bottom:var(--s2);
  }}
  .al-tile-head svg {{ flex:none; }}
  .al-tile-value {{
    font-size:1.9rem; font-weight:680; color:var(--ink);
    line-height:1.1; letter-spacing:-.02em;
  }}
  .al-tile-value .al-unit {{ font-size:1rem; color:var(--ink-dim); font-weight:500; }}
  .al-tile-delta {{
    display:flex; align-items:center; gap:5px;
    font-size:.75rem; margin-top:6px; color:var(--ink-dim);
  }}
  .al-up   {{ color:var(--good); }}
  .al-down {{ color:var(--critical); }}
  .al-flat {{ color:var(--muted); }}

  /* Accent de marque sur la tuile pilote */
  .al-tile.al-lead {{ border-color:rgba(255,179,0,.35); }}
  .al-tile.al-lead .al-tile-head {{ color:var(--amber); }}

  /* ── Cartes de graphique ────────────────────────────────────────── */
  .al-card-title {{
    display:flex; align-items:center; justify-content:space-between;
    font-size:.9rem; font-weight:620; color:var(--ink);
    margin:0 0 2px 0;
  }}
  .al-card-sub {{ font-size:.75rem; color:var(--muted); margin-bottom:var(--s1); }}

  /* Cible le conteneur d'une carte : celui dont le premier élément est un
     titre .al-card-title. Le testid de Streamlit a changé en 1.5x
     (stVerticalBlockBorderWrapper → stLayoutWrapper) : vérifier ce sélecteur
     après une montée de version de Streamlit. */
  [data-testid="stLayoutWrapper"]:has(
      > [data-testid="stVerticalBlock"]
      > [data-testid="stElementContainer"]
      > [data-testid="stMarkdown"] .al-card-title) {{
    background:var(--surface); border:1px solid var(--line);
    border-radius:10px; padding:var(--s3);
  }}

  /* ── État vide ──────────────────────────────────────────────────── */
  .al-empty {{
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    gap:var(--s1); padding:var(--s5) var(--s3); color:var(--muted);
    border:1px dashed var(--line); border-radius:8px; text-align:center;
  }}
  .al-empty-title {{ font-size:.86rem; color:var(--ink-dim); font-weight:560; }}
  .al-empty-hint  {{ font-size:.76rem; }}

  /* ── Onglets ────────────────────────────────────────────────────── */
  .stTabs [data-baseweb="tab-list"] {{ gap:var(--s4); border-bottom:1px solid var(--line); }}
  .stTabs [data-baseweb="tab"] {{
    color:var(--ink-dim); font-weight:560; font-size:.88rem;
    padding:var(--s1) 0; background:transparent;
  }}
  .stTabs [aria-selected="true"] {{ color:var(--amber) !important; }}
  .stTabs [data-baseweb="tab-highlight"] {{ background:var(--amber); }}

  /* ── Sidebar ────────────────────────────────────────────────────── */
  [data-testid="stSidebar"] {{ background:var(--surface); border-right:1px solid var(--line); }}
  .al-logo {{
    display:flex; align-items:center; gap:var(--s1);
    font-size:1.05rem; font-weight:700; color:var(--ink); letter-spacing:-.01em;
  }}
  .al-logo-dot {{
    width:9px; height:9px; border-radius:50%; background:var(--amber);
    box-shadow:0 0 0 3px rgba(255,179,0,.16);
  }}
  .al-logo-sub {{
    font-size:.72rem; color:var(--muted); text-transform:uppercase;
    letter-spacing:.1em; margin:2px 0 var(--s3) 18px;
  }}
  .al-garage-row {{
    display:flex; align-items:center; gap:var(--s1);
    font-size:.78rem; color:var(--ink-dim); padding:3px 0;
  }}
  .al-garage-row svg {{ flex:none; width:13px; height:13px; }}

  /* ── Tableaux : chiffres alignés verticalement ──────────────────── */
  [data-testid="stDataFrame"] {{ font-variant-numeric:tabular-nums; }}

  /* ── Accessibilité ──────────────────────────────────────────────── */
  button:focus-visible, [role="tab"]:focus-visible, select:focus-visible {{
    outline:2px solid var(--amber); outline-offset:2px;
  }}
  @media (prefers-reduced-motion:reduce) {{
    .al-tile {{ transition:none; }}
    .al-tile:hover {{ transform:none; }}
  }}
</style>
"""


# ── Composants ───────────────────────────────────────────────────────────────

def stat_tile(
    icon: str,
    label: str,
    value: str,
    unit: str = "",
    delta: str | None = None,
    delta_dir: str = "flat",   # "up" | "down" | "flat"
    lead: bool = False,
) -> str:
    """Une tuile KPI. `delta_dir` porte une flèche : la couleur ne suffit jamais."""
    # Important : le HTML doit rester sur UNE ligne sans indentation — Streamlit
    # passe la chaîne au moteur Markdown, qui transformerait toute ligne indentée
    # de 4 espaces en bloc de code affiché tel quel.
    arrow = {"up": _ARROW_UP, "down": _ARROW_DOWN}.get(delta_dir, "")
    delta_html = (
        f'<div class="al-tile-delta al-{delta_dir}">{arrow}<span>{delta}</span></div>'
        if delta else ""
    )
    unit_html = f' <span class="al-unit">{unit}</span>' if unit else ""
    return (
        f'<div class="al-tile{" al-lead" if lead else ""}">'
        f'<div class="al-tile-head">{ICONS.get(icon, "")}<span>{label}</span></div>'
        f'<div class="al-tile-value">{value}{unit_html}</div>'
        f'{delta_html}'
        f'</div>'
    )


def tiles_row(tiles: list[str]) -> str:
    return f'<div class="al-tiles">{"".join(tiles)}</div>'


def card_title(title: str, subtitle: str = "") -> str:
    sub = f'<div class="al-card-sub">{subtitle}</div>' if subtitle else ""
    return f'<div class="al-card-title">{title}</div>{sub}'


def empty_state(title: str, hint: str = "") -> str:
    hint_html = f'<div class="al-empty-hint">{hint}</div>' if hint else ""
    return (
        f'<div class="al-empty">{ICONS["empty"]}'
        f'<div class="al-empty-title">{title}</div>{hint_html}'
        f'</div>'
    )


# ── Mise en forme commune des graphiques Plotly ──────────────────────────────

def style_fig(fig, height: int = 260, showlegend: bool = False, x_grid: bool = False):
    """Applique la charte : surface transparente, grille discrète, hover lisible."""
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=8, t=8, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family='system-ui, -apple-system, "Segoe UI", sans-serif',
            size=12, color=INK_DIM,
        ),
        showlegend=showlegend,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(size=11, color=INK_DIM), bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(
            bgcolor=SURFACE, bordercolor=LINE,
            font=dict(color=INK, size=12,
                      family='system-ui, -apple-system, "Segoe UI", sans-serif'),
        ),
        bargap=0.34,
    )
    fig.update_xaxes(
        showgrid=x_grid, gridcolor=LINE, gridwidth=1,
        zeroline=False, linecolor=LINE, tickcolor=LINE,
        tickfont=dict(color=MUTED, size=11),
    )
    fig.update_yaxes(
        showgrid=not x_grid, gridcolor=LINE, gridwidth=1,
        zeroline=False, linecolor="rgba(0,0,0,0)", tickcolor="rgba(0,0,0,0)",
        tickfont=dict(color=MUTED, size=11),
    )
    return fig
