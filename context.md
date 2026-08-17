# 🚗 CONTEXT.MD — AgentVoc (Voice Agent Garage)
> À coller en début de nouvelle conversation pour reprendre le projet

---

## 📊 État du projet — mis à jour le 17/08/2026

> Les sections détaillées plus bas sont datées du 14/08 (session de travail). Ce tableau
> de bord est la **vue d'ensemble** ; le détail de chaque point est dans les sections
> correspondantes. Tout est poussé sur `origin/main` (dépôt `DamienL347/AgentVoc`).

**Suite de tests : 84 verts** (unitaires + intégration rejouée contre la vraie base Supabase,
fournisseurs simulés — aucun coût, aucun SMS réel).

### Ce qui est fait et validé sans dépense
| Bloc | Sujet | État |
|------|-------|------|
| — | Dashboard de monitoring (étape 11) | ✅ à la charte AgentLumy |
| — | Traçabilité des SMS/emails en base | ✅ |
| — | Schéma SQL versionné (`scripts/schema.sql`) | ✅ |
| — | Mode fournisseurs simulés (`PROVIDER_MODE=fake`) | ✅ socle de tout le reste |
| A | Simulateur d'appel (`scripts/simulate_call.py`) | ✅ 7 scénarios |
| B | Cas d'usage V1 complétés (véhicule prêt, humain, créneau pris, n° masqué) | ✅ |
| C | Rappels de RDV J-1 et H-2 | ✅ code prêt, activé par Cloud Scheduler |
| D | Déploiement Cloud Run (Dockerfile + CI/CD) | ✅ prêt, non déployé |

### Bugs bloquants trouvés et corrigés pendant ces sessions
Chacun était **invisible** (échec silencieux ou masqué par un fallback), et aurait cassé la
prestation en production :
1. `get_garage_by_phone()` — aucun appel ne pouvait identifier son garage (colonnes inexistantes).
2. Cal.com `create_booking` — RDV créés dans **aucun agenda** pendant que l'agent disait « confirmé ».
3. Cal.com réponses v2 — `calcom_uid` vide → RDV impossibles à modifier/annuler ensuite.
4. `on_call_ended` — statut métier écrasé → **taux de conversion du dashboard faux**.

### Ce qui reste — SANS dépense (faisable maintenant)
- **Feature « garage en vacances »** : l'agenda Cal.com reste la source de vérité (le garage
  y bloque ses congés) ; quand aucun créneau n'est dispo sur la fenêtre courante, élargir la
  recherche et annoncer la réouverture. Décision actée, voir section « Reste à traiter ».
- **Étape 12 — Optimisation** : latence < 800 ms, coût réel par appel, réglage des prompts.
- **RGPD** : l'annonce d'enregistrement est déjà dans le prompt ; reste la politique de
  confidentialité et la durée de conservation.

### Ce qui reste — AVEC dépense (reporté au mois prochain, sur décision de Damien)
- Numéro FR dédié chez Twilio (compte payant + justificatif, délai de quelques jours).
- Plan Cal.com plateforme (managed users, uniquement pour l'onboarding auto).
- Supabase Pro (le plan gratuit se met en pause après ~1 semaine d'inactivité).
- Carte bancaire pour activer la facturation Google Cloud (usage réel ~0 €, mais exigée).
- **Bascule finale** : `PROVIDER_MODE=real`, rejouer le simulateur + les tests, un appel réel.

---

## 👤 Profil développeur
- **Nom** : Damien Lauger
- **Profil** : Business Analyst + Chef de projet IA + Python + SQL
- **Niveau** : Intermédiaire (pas débutant)
- **OS** : Windows 11
- **IDE** : VS Code
- **Dossier projet** : `C:\Users\DamienLauger\Desktop\AgentVoc`

---

## 🎯 Projet
Agent IA vocal autonome pour **garagistes et dépanneurs** capable de :
- Répondre aux appels entrants 24/7
- Comprendre la demande client en français
- Proposer et réserver des rendez-vous
- Synchroniser avec l'agenda
- Détecter les urgences et transférer

**Nom commercial** : AgentLumy
**Domaine** : agentlumy.com
**Email** : rdv@agentlumy.com

---

## 🛠️ Stack technique validé

| Brique | Outil | Statut |
|---|---|---|
| LLM | Claude Haiku (`claude-haiku-4-5`) | ✅ Configuré |
| Orchestration vocale | Vapi | ✅ Configuré |
| Téléphonie | Twilio (numéro US trial) | ✅ Configuré |
| STT | Deepgram Nova-2 FR | ✅ Configuré |
| TTS | Cartesia Sonic Multilingual | ✅ Configuré |
| Backend | Python FastAPI (port 8080) | ✅ Fonctionnel |
| Base de données | Supabase (PostgreSQL) | ✅ Tables créées |
| Agenda | Cal.com + Google Calendar | ✅ Configuré |
| SMS | Twilio SMS | ✅ Intégré |
| Email | Resend (agentlumy.com) | ✅ Configuré |
| Hébergement (prod) | Google Cloud Run (europe-west1) | ⏳ Phase 3 |
| Tunnel local | ngrok | ✅ Fonctionnel |
| Versioning | GitHub (repo privé AgentVoc) | ✅ Pushé |

---

## 📁 Structure du projet

```
AgentVoc/
├── app/
│   ├── __init__.py
│   ├── main.py                    ✅ Entry point FastAPI
│   ├── config.py                  ✅ Settings Pydantic
│   ├── api/
│   │   ├── __init__.py
│   │   ├── webhooks.py            ✅ Routes webhook Vapi
│   │   └── tools.py               ✅ Routes tool calls (9 endpoints)
│   ├── core/
│   │   ├── __init__.py
│   │   └── call_handler.py        ✅ Logique métier (9 tool handlers)
│   ├── db/
│   │   ├── __init__.py
│   │   └── supabase_client.py     ✅ Client Supabase + BaseRepository
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── vapi_client.py         ✅ Client Vapi complet
│   │   ├── calcom_client.py       ✅ Client Cal.com v2
│   │   ├── twilio_sms.py          ✅ Client Twilio SMS
│   │   └── resend_email.py        ✅ Client Resend emails HTML
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py             ✅ Modèles Pydantic
│   └── prompts/
│       ├── __init__.py
│       ├── system_prompt.py       ✅ Moteur génération dynamique
│       └── templates/
│           ├── garage_mecanique_v1.txt   ✅ Prompt garagiste
│           └── depanneur_v1.txt          ✅ Prompt dépanneur
├── scripts/
│   ├── setup_supabase_v2.sql      ✅ Schéma BDD complet (exécuté)
│   └── seed_data.sql              ✅ Données de test (injectées)
├── tests/
├── docs/
├── venv/
├── .env                           ✅ Toutes les clés configurées
├── .env.example                   ✅ Template
├── .gitignore                     ✅
├── requirements.txt               ✅
└── README.md                      ✅
```

---

## 🗄️ Base de données Supabase

**9 tables créées et opérationnelles :**

```
garages              → Clients de la plateforme (multi-tenant)
garage_services      → Services proposés par garage
end_clients          → Clients finaux des garages
vehicles             → Véhicules des clients
calls                → Historique de tous les appels ← table centrale
appointments         → Rendez-vous pris/modifiés/annulés
notifications        → SMS et emails envoyés
agent_prompts        → Prompts versionnés par garage
audit_logs           → Traçabilité complète
```

**Fonctionnalités BDD :**
- ✅ Row Level Security (RLS) multi-tenant
- ✅ Triggers updated_at automatiques
- ✅ Trigger calcul ends_at (appointments)
- ✅ Triggers stats clients automatiques
- ✅ Fonction get_garage_stats() pour dashboard
- ✅ 2 garages de test + clients + appels + RDV seedés

---

## 🎙️ Agent Vapi configuré

**Assistant créé dans Vapi avec :**
- LLM : Claude Haiku (temperature 0.3, max 250 tokens)
- STT : Deepgram Nova-2 FR
- TTS : Cartesia Sonic Multilingual (voix FR choisie)
- First message : "Bonjour, je suis Léa du Garage Martin. Comment puis-je vous aider ?"
- Background denoising : ON
- Call recording : ON
- Max duration : 600s

**9 tools configurés :**
```
check_availability       → Vérifie créneaux Cal.com
create_appointment       → Crée RDV Cal.com + Supabase
get_appointment_by_phone → Retrouve RDV par téléphone
update_appointment       → Modifie un RDV
cancel_appointment       → Annule un RDV
send_confirmation        → SMS + email confirmation
transfer_call            → Transfère vers patron
send_sms_alert           → Alerte SMS urgence
take_message             → Message pour rappel
```

---

## 📋 Cas d'usage gérés (V1)

| Cas | Description | Statut |
|---|---|---|
| Cas 1 | Prise de RDV intervention planifiée | ✅ |
| Cas 2 | Demande d'information basique | ✅ |
| Cas 3 | Demande de devis simple | ✅ |
| Cas 4 | Modification/annulation RDV | ✅ |
| Cas 5 | Dépannage non urgent | ✅ |
| Cas 8 | Détection mécontentement → transfert | ✅ |
| Urgence | Escalation path 24/7 | ✅ |

---

## ✅ Phases complétées

### Phase 1 — Fondations ✅
- Cadrage fonctionnel (cible, cas d'usage, modèle de données)
- Stack technique validé
- Environnement de travail configuré

### Phase 2 — MVP ✅
- Étape 4 : Schéma BDD Supabase (9 tables + RLS + triggers)
- Étape 5 : System prompts garagiste + dépanneur
- Étape 6 : Configuration Vapi + Backend FastAPI
- Étape 7 : Intégrations Cal.com + Twilio + Resend
- Étape 8 : ngrok + Webhook Vapi configuré
- Étape 9 : **Premier appel vocal réussi ✅**
  - Webhooks reçus : speech-update, status-update, end-of-call-report
  - Appel enregistré en Supabase (59 secondes)
  - Tous les HTTP 200 OK

---

## ⏳ Phase 3 — Industrialisation (À FAIRE)

```
Étape 10 : Architecture multi-tenant complète
           → Onboarding automatique d'un nouveau garage
           → Création assistant Vapi dynamique
           → Configuration Cal.com par garage

Étape 11 : Dashboard de monitoring
           → Metabase ou Streamlit
           → KPIs : taux conversion, appels manqués, RDV pris
           → Vue par garage (multi-tenant)

Étape 12 : Optimisation
           → Latence (objectif < 800ms)
           → Coûts par appel
           → Qualité vocale

Étape 13 : Déploiement Google Cloud Run
           → Dockerfile
           → CI/CD GitHub Actions
           → Variables d'env Secret Manager
           → URL publique fixe (remplace ngrok)
```

## ⏳ Phase 4 — Commercialisation (À FAIRE)

```
Étape 14 : Pricing & offre commerciale
Étape 15 : Acquisition premiers clients (garagistes Toulouse)
Étape 16 : Onboarding & SLA
```

---

## 💰 Coûts mensuels estimés (3 clients)

| Poste | Coût/mois |
|---|---|
| Vapi (~500 min × 3 clients) | ~75€ |
| Twilio (numéros + SMS) | ~15€ |
| Anthropic (Claude Haiku) | ~10€ |
| Cartesia TTS | ~20€ |
| Supabase | 0€ (gratuit) |
| Cal.com | ~15€ |
| Google Cloud Run | ~2€ |
| Resend | 0€ (gratuit) |
| **TOTAL** | **~137€/mois** |

**Marge avec 3 clients à 400€/mois : ~88%** 🚀

---

## 🔧 Commandes utiles

```powershell
# Lancer le serveur local
cd C:\Users\DamienLauger\Desktop\AgentVoc
venv\Scripts\activate
uvicorn app.main:app --reload --port 8080

# Lancer ngrok (nouveau terminal)
ngrok http 8080

# Swagger docs
http://localhost:8080/docs

# Dashboard ngrok
http://127.0.0.1:4040
```

---

## 📝 Notes importantes

- ⚠️ URL ngrok change à chaque redémarrage → mettre à jour APP_BASE_URL dans .env
- ⚠️ Numéro Twilio US trial → passer à numéro FR avant premier client
- ⚠️ Google OAuth redirect URI à mettre à jour après déploiement Cloud Run
- ✅ Toujours avoir 2 terminaux ouverts : uvicorn + ngrok
- ✅ Port applicatif : 8080 (compatibilité Cloud Run)

---

*Généré le 07/05/2026 — Fin de Phase 2*


## ✅ Étape 10 — Multi-tenant (COMPLÈTE)

### Fichiers créés/modifiés
- `scripts/setup_multitenant_v1.sql` ✅ (exécuté en Supabase)
- `app/services/__init__.py` ✅
- `app/services/onboarding_service.py` ✅
- `app/api/onboarding.py` ✅
- `app/middleware/__init__.py` ✅
- `app/middleware/tenant_resolver.py` ✅
- `app/models/schemas.py` ✅ (OnboardingRequest, OnboardingResult ajoutés)
- `app/integrations/calcom_client.py` ✅ (create_managed_user, create_schedule, create_event_type ajoutés)
- `app/integrations/vapi_client.py` ✅ (create_phone_number ajouté, modèle corrigé)
- `app/prompts/system_prompt.py` ✅ (conversion schedule onboarding corrigée)

### Points à finir en production
- Cal.com managé users → vérifier compatibilité plan
- Twilio ↔ Vapi linking → activé seulement en APP_ENV=production
- Upgrader compte Twilio pour numéros FR dédiés

## ✅ Correctifs sécurité & conformité (17/07/2026)

- **Signature HMAC obligatoire** sur `/webhooks/vapi` ET `/tools/*` (avant : contournable en
  omettant l'en-tête ; les tools ne vérifiaient rien) → `app/api/security.py` (dépendance
  `require_vapi_signature`, fail-closed en production)
- **Vérification caller ID** : `get_appointment_by_phone` cherche sur le numéro réel de
  l'appelant ; `update/cancel_appointment` vérifient la propriété du RDV (garage + numéro)
  → `_check_appointment_ownership()` dans call_handler
- **Dates en français parlé** pour TTS et SMS → `app/utils/datetime_fr.py`
  ("samedi 19 juillet à 14h30" au lieu de l'ISO brut)
- **Normalisation téléphone E.164** → `app/utils/phone.py` (compare 06… et +336…)
- **Conformité AI Act/CNIL** : first message = "l'assistante vocale de X. Cet appel peut être
  enregistré." ; règle "ne jamais révéler l'IA" remplacée par transparence obligatoire
- **Idempotence** : webhook call.started rejoué → pas de doublon en BDD
- **Tests** : 19 tests unitaires dans `tests/unit/` (signature, dates, téléphones) — tous verts
- **Fix environnement** : starlette 1.x avait cassé fastapi 0.115 (app ne démarrait plus) →
  fastapi upgradé en 0.139.2, requirements.txt mis à jour (+ deps dashboard épinglées)

### Reste à faire (sécurité)
- Fallback Vapi/Twilio si backend down (rediriger vers le vrai numéro du garage)
- Confirmation vocale (nom + date) avant annulation même pour le titulaire
- Rappels J-1 SMS + rapport hebdo (features à forte valeur commerciale)

## 📁 Portfolio commercial (17/07/2026)

Dossier : `portfolio/` dans le projet AgentVoc
(site vitrine agentlumy.com + 2 maquettes garages personnalisables + one-pager PDF)

## ✅ Étape 11 — Dashboard monitoring (COMPLÈTE — 13/08/2026)

`dashboard.py` (Streamlit) — `streamlit run dashboard.py`, port 8520.
Validé contre les vraies données Supabase (5 appels, 2 RDV, 19 garages).

### Corrections apportées (le dashboard ne pouvait pas fonctionner avant)
- **Clé Supabase** : lisait `SUPABASE_SERVICE_KEY` (inexistant) → retombait sur la clé anon,
  RLS renvoyait des tables vides. Corrigé en `SUPABASE_SERVICE_ROLE_KEY` (comme `app/config.py`).
- **6 colonnes inexistantes** référencées : `calls.status` → `call_status` ;
  `appointments.service_type` → `title` ; `notifications.type` → `channel` ;
  `onboarding_logs.step_number`/`step_name` → `step`.
- **Valeurs d'ENUM** : le code cherchait des valeurs anglaises (`missed`, `confirmed`,
  `in_progress`) alors que les ENUMs Supabase sont **en français**
  (`abandonne`, `confirme`, `pending`…). Table de libellés ajoutée en tête de fichier.
- **Taux de conversion** : basé sur `call_status = 'rdv_pris'` (et non le simple ratio
  RDV créés / appels, faussé par les décalages de période).

### Ajouts
- Filtre période étendu (7j / 30j / 90j / 1 an / tout l'historique) — les données seed
  dataient de mai, l'ancien maximum de 90 jours affichait un dashboard vide.
- Filtres garage + période pilotables par URL (`?garage=…&periode=…`) → vue partageable.
- KPIs urgences / transferts, nature des demandes, taux d'annulation des RDV, RDV à venir.
- Onglet Onboarding : graphique de fiabilité par étape (quelle étape échoue le plus).
- Dates affichées en Europe/Paris, séries journalières sans trou.

### ⚠️ Trous découverts pendant l'étape 11
1. ✅ **CORRIGÉ** — La table `notifications` n'était jamais écrite (voir ci-dessous).
2. ⏳ **Le schéma SQL n'est plus versionné.** `scripts/` ne contenait qu'un `.gitkeep` :
   `setup_supabase_v2.sql`, `setup_multitenant_v1.sql` et `seed_data.sql` n'ont jamais été
   commités et n'existent plus sur le disque. Le schéma des 10 tables n'existe QUE dans
   Supabase. `scripts/dump_schema.py` est prêt mais **bloqué** : voir ci-dessous.
3. **16 garages sur 19 sont en `onboarding_status = failed`** (échec à `buy_twilio_number`,
   compte Twilio trial). À nettoyer avant la mise en production.
4. Le projet Supabase gratuit **se met en pause après ~1 semaine d'inactivité** (arrivé en
   août 2026 : le hostname disparaît même du DNS). Bloquant si un client appelle.

## ✅ Traçabilité des notifications (14/08/2026)

Avant : `call_handler` appelait `twilio_client.send_sms()` / Resend directement, sans rien
écrire en base. Aucune preuve qu'une confirmation était partie (litige client), et le SID
Twilio / l'id Resend étaient jetés puisque les clients ne retournaient qu'un booléen.

- `app/integrations/send_result.py` — `SendResult(ok, provider_id, error)`, avec `__bool__`
  pour rester compatible avec l'ancien contrat `if sms_sent:`.
- Twilio et Resend retournent désormais un `SendResult` porteur du SID / de l'id.
- `app/services/notification_service.py` — **passage obligé** de tout envoi sortant :
  envoie puis écrit dans `notifications` (canal, destinataire, statut, sent_at, id
  fournisseur, message d'erreur). L'écriture est encapsulée : un échec de traçabilité ne
  casse jamais l'appel en cours.
- Les 5 points d'envoi de `call_handler` passent par le service ; `_get_call_id()` rattache
  chaque notification à l'appel qui l'a déclenchée. Plus aucun appel direct aux clients
  Twilio/Resend en dehors du service (vérifié par grep).
- 6 tests unitaires ajoutés (`tests/unit/test_notification_service.py`) — **25 tests verts**.
- Validé en conditions réelles : insertion dans la vraie base Supabase puis nettoyage.

## ✅ BUG BLOQUANT corrigé le 14/08/2026 — `get_garage_by_phone()`

**Aucun appel entrant ne pouvait identifier son garage.** La fonction SQL utilisée par
`app/middleware/tenant_resolver.py` échoue systématiquement :

    ERROR 42703: column g.timezone does not exist

Elle sélectionne `g.timezone` (n'a jamais existé) et `g.is_active` (la colonne réelle est
`status`), et déclare `garage_type` en `text` alors que c'est un enum.

Le bug était **invisible** : le middleware avale l'exception pour ne jamais bloquer un appel
et se contente de logguer « Aucun garage trouvé ». Le multi-tenant était donc réputé
« testé OK » alors que la résolution n'a jamais fonctionné. C'est l'export du schéma qui l'a
révélé — argument de plus pour versionner le SQL.

**Correctif appliqué** (`scripts/fix_get_garage_by_phone.sql`, exécuté dans le SQL Editor).
Il accepte les garages `active` **et** `trial` (les garages onboardés démarrent en `trial` :
filtrer sur « actif » seul les aurait tous exclus) et fige `search_path` (exigé par
`SECURITY DEFINER`). Vérifié : le numéro `+14722383374` résout bien Garage Perrin Lyon Sud.

**Garde-fou anti-régression** : `tests/integration/test_tenant_resolver_rpc.py` (3 tests)
appelle la vraie RPC et vérifie les champs retournés — une colonne renommée en base fera
désormais échouer les tests au lieu de casser silencieusement les appels.
Suite complète : **28 tests verts** (25 unitaires + 3 intégration).

⚠️ `scripts/schema.sql` a été réaligné sur la fonction corrigée : recréer la base à partir
de ce fichier aurait sinon réintroduit le bug.

### Deux réglages incomplets révélés par le test (à traiter avant le 1er client)
- `calcom_event_type_id = 0` sur Garage Perrin → Cal.com n'est pas réellement rattaché,
  la prise de RDV échouera (déjà connu : managed users à vérifier selon le plan Cal.com).
- `transfer_sms_number = NULL` → aucune alerte SMS d'urgence ne partira pour ce garage
  (`_handle_send_sms_alert` répond « Numéro d'alerte non configuré »).

## ✅ Export du schéma SQL — FAIT (14/08/2026)

`scripts/schema.sql` — 10 tables, 485 lignes, versionné. Le modèle de données ne vit plus
uniquement dans Supabase.

Deux chemins pour le régénérer :

**A. Sans mot de passe (recommandé) — via le SQL Editor**
1. Supabase → SQL Editor → New query → coller `scripts/export_schema.sql` → Run
2. Le résultat tient dans une seule cellule `ddl` → « Download CSV »
3. `venv\Scripts\python.exe scripts/csv_to_schema.py <fichier.csv>` → écrit `scripts/schema.sql`

**B. Avec le mot de passe Postgres** — `scripts/dump_schema.py` fait tout en une commande.
Le mot de passe n'est **jamais affiché** par Supabase : il faut le réinitialiser via
*Project Settings* (bas de la barre latérale gauche, au-dessus de l'avatar — pas les réglages
de compte) → section **Configuration** → **Database** → « Reset database password ».
Puis `SUPABASE_DB_PASSWORD=…` dans `.env`.

`scripts/dump_schema.py` et `scripts/export_schema.sql` produisent le même contenu :
types, tables, contraintes, index, fonctions, triggers, vues, RLS + policies.

**Blocage rencontré sur la voie B** : le mot de passe Postgres de `DATABASE_URL` est invalide
(`password authentication failed for user "postgres"`). Il n'avait jamais été testé —
l'application n'utilise que l'API REST, jamais la connexion directe. Le mot de passe
contient par ailleurs des caractères (`@`, `]`) non URL-encodés qui cassent le parsing
de l'URI.

**Pour débloquer** : Supabase → Project Settings → Database → *Database password*
(« Reset database password » si perdu), puis ajouter dans `.env` :

    SUPABASE_DB_PASSWORD=<le mot de passe, tel quel, sans encodage>

puis `venv\Scripts\python.exe scripts/dump_schema.py`.

Note : le host direct `db.<ref>.supabase.co` ne résout qu'en **IPv6**. Sans IPv6, prendre
la chaîne « Session pooler » (IPv4) et renseigner `SUPABASE_DB_HOST` / `SUPABASE_DB_USER`.

## 🎨 Charte du dashboard (14/08/2026)

`dashboard_theme.py` — tokens, CSS et composants ; `dashboard.py` ne contient que la logique.

- Palette **carbone + ambre** alignée sur `portfolio/site/index.html` (le dashboard est un
  outil AgentLumy, pas d'un garage client). Le violet d'origine ne correspondait à rien.
- Les **couleurs de séries ne sont pas les couleurs de marque** : l'ambre `#ffb300` sert
  d'accent d'interface uniquement. Les séries utilisent une palette validée
  (`#c98500, #199e70, #3987e5, #d55181, #9085e9, #e66767`) : bande de luminosité, plancher
  de chroma, séparation daltonisme (ΔE ≥ 8), contraste ≥ 3:1 sur la surface `#14171d`.
  **L'ordre des couleurs est le mécanisme de sécurité CVD — ne pas permuter sans re-valider.**
- Statuts (`good/warning/serious/critical`) réservés, jamais réutilisés comme série, et
  toujours accompagnés d'une icône + d'un libellé (jamais la couleur seule).
- Icônes SVG (Lucide) au lieu d'emojis ; tuiles KPI en HTML ; tableaux en `tabular-nums`.
- Le **donut « Issue des appels » a été remplacé par une barre horizontale triée** : un donut
  à 10 parts de valeurs proches est illisible (au-delà de 6 classes, le reste va dans « Autres »).
- Responsive vérifié (desktop / tablette, pas de scroll horizontal), focus visible au clavier,
  `prefers-reduced-motion` respecté.

⚠️ Piège Streamlit : le HTML injecté via `st.markdown` doit tenir sur **une seule ligne sans
indentation**, sinon le moteur Markdown transforme les lignes indentées de 4 espaces en blocs
de code affichés tels quels. Et Streamlit **ne recharge pas les modules importés** : après une
modification de `dashboard_theme.py`, redémarrer le serveur (un simple refresh ne suffit pas).

## ✅ Mode fournisseurs simulés — PROVIDER_MODE (14/08/2026)

Permet de valider **tout le produit sans compte payant** : ni numéro Twilio FR, ni plan
Cal.com plateforme, ni crédits consommés.

    PROVIDER_MODE=fake   # dans .env — Twilio, Cal.com, Vapi et Resend simulés
    PROVIDER_MODE=real   # bascule vers le réel, aucun autre changement de code

**Principe : la simulation se fait au niveau du transport HTTP**, jamais au niveau métier.
Le vrai code continue de tourner (normalisation des numéros, construction des messages,
parsing et formatage FR des créneaux, gestion d'erreurs) ; seul l'aller-retour réseau est
feint. Un mock posé sur les méthodes métier ne testerait plus que le mock.

Règle à tenir : **le simulateur ne doit jamais être plus permissif que l'API réelle.**
Il reproduit la structure de réponse v2 de Cal.com à l'identique — c'est précisément ce
qui a fait apparaître le bug d'enveloppe `data` ci-dessous.

Implémentation : `app/integrations/fake_transport.py`. `SENT_LOG` journalise tout ce qui
« serait parti » (SMS, emails, réservations, achats de numéro) — le harnais de test peut
vérifier qu'un SMS est bien parti sans qu'aucun SMS ne parte.

## 🔴 Deux bugs Cal.com trouvés grâce au mode simulé (14/08/2026)

Tous deux échouaient **en silence, vers un repli** — jamais d'erreur visible.

**1. `create_booking` envoyait `calcom_user_id` dans le champ `eventTypeId`.**
Mauvaise colonne (vide sur tous les garages) et confusion entre « user id » et
« event type id ». Cal.com refusait, on repliait en base locale : **le RDV n'existait dans
aucun agenda pendant que l'agent annonçait « votre rendez-vous est confirmé »**. Le client
raccroche confiant, le garagiste n'a rien. C'est le défaut qui aurait le plus abîmé la
prestation. Corrigé : lecture de `calcom_event_type_id`, avec court-circuit explicite quand
l'agenda n'est pas rattaché (`0` est traité comme une absence, pas comme un identifiant).

**2. Les réponses de l'API v2 sont encapsulées sous `data`, le code lisait à la racine.**
`calcom_uid` revenait donc vide : le RDV devenait impossible à modifier ou annuler ensuite,
alors que tout semblait avoir réussi. Corrigé pour les créneaux et les réservations.

⚠️ Conséquence à garder en tête : tant qu'un garage n'a pas de `calcom_event_type_id`
valide, `check_availability` propose des **créneaux de repli inventés**, absents de tout
agenda. Ils sont marqués `is_fallback: true` — à rendre visible dans le dashboard.

Tests : `tests/unit/test_calcom_parsing.py` (6 tests). Suite complète : **34 tests verts**.

## ✅ .env.example recréé (14/08/2026)

Il avait disparu comme les scripts SQL. Sans lui, impossible de savoir quelles variables
sont requises — bloquant pour le déploiement Cloud Run. Reconstruit depuis `app/config.py`,
sans aucun secret.

## ✅ Simulateur d'appel — bloc A (14/08/2026)

Rejoue un parcours client complet contre le backend réel : **sans téléphone, sans Vapi,
sans crédits**. Jusqu'ici, vérifier un parcours coûtait un vrai appel — c'est pour ça que
des pannes dures sont restées invisibles pendant des mois.

    venv\Scripts\python.exe scripts/simulate_call.py --list
    venv\Scripts\python.exe scripts/simulate_call.py --scenario rdv
    venv\Scripts\python.exe scripts/simulate_call.py --scenario urgence
    venv\Scripts\python.exe scripts/simulate_call.py --sans-agenda   # garage non rattaché

5 scénarios : rdv · annulation · urgence · mecontentement · message.
La sortie affiche le dialogue (ce que dirait l'agent) **et** un bilan de ce qui a réellement
été enregistré — les deux peuvent diverger, c'est justement ce qu'on cherche à voir.

Ce qui est réel : FastAPI complet, signature HMAC (le harnais signe comme Vapi, il ne
contourne pas la sécurité), middlewares, logique métier, base Supabase.
Ce qui est simulé : uniquement le réseau vers Twilio, Cal.com, Vapi, Resend.

Isolation : chaque simulation crée un **garage jetable** supprimé à la fin. Les FK sont en
ON DELETE CASCADE, donc appels, RDV et notifications partent avec. Aucune donnée réelle
n'est touchée.

Fichiers : `tests/simulator/` (harness + payloads), `scripts/simulate_call.py` (CLI),
`tests/integration/test_scenarios_usage.py` (13 scénarios en pytest).
**Suite complète : 47 tests verts.**

## 🔴 Bug trouvé par le simulateur — le taux de conversion était faux

`on_call_ended` écrasait systématiquement `call_status` par le statut déduit de
`endedReason`. Un RDV pris était donc **recompté en `information_donnee`** dès que l'agent
raccrochait normalement ; un transfert devenait `abandonne` si le client raccrochait.

Conséquence : le KPI principal du dashboard — le taux de conversion — mesurait n'importe
quoi, et les 5 appels de test en base sont probablement mal classés.

Correction : les statuts **métier** (`rdv_pris`, `rdv_modifie`, `rdv_annule`,
`devis_propose`, `message_laisse`, `transfere_humain`, `urgence_signalee`) décrivent ce que
l'appel a produit et priment sur les statuts **techniques** (`abandonne`, `erreur`,
`information_donnee`) qui ne décrivent que sa fin. Verrouillé par 3 tests.

## ✅ Cas d'usage V1 complétés — bloc B (14/08/2026)

Les 6 cas d'origine ne couvraient pas des situations quotidiennes en garage. Fil conducteur
de tous ces ajouts : **l'agent ne doit jamais promettre ce qu'il ne peut pas tenir.**

**CAS 9 — « Ma voiture est-elle prête ? »** (nouvel outil `check_vehicle_status`)
Souvent le 2ᵉ motif d'appel. L'agent n'a aucun accès au suivi de l'atelier : il le dit, puis
route — mise en relation si le garage est ouvert, prise de message sinon. Il remonte au
passage le dernier RDV connu du client, utile à qui reprend l'appel. Interdiction explicite
d'inventer un état d'avancement : un client qui se déplace pour rien ne revient pas.

**CAS 10 — Le client veut un humain**
Transfert immédiat, sans insister. Surtout : **on ne transfère plus vers un téléphone qui ne
décrochera pas.** Sans numéro configuré ou hors horaires, l'agent l'annonce et bascule sur
la prise de message. Tomber dans le vide est pire que ne pas transférer, en particulier pour
un client déjà mécontent. (1 garage sur 3 en base n'a pas de `transfer_phone_number`.)

**CAS 11 — Numéro masqué** (`phone.is_anonymous`)
Sans numéro : ni rappel, ni SMS de confirmation, ni recherche de RDV. L'agent doit demander
le numéro avant de promettre quoi que ce soit.

**CAS 12 — Créneau pris pendant la conversation**
Entre l'annonce d'un créneau et son acceptation, il s'écoule une minute — assez pour qu'il
soit pris ailleurs. Détection de **chevauchement** (pas seulement d'heure de début
identique : une vidange de 45 min posée au milieu d'une révision de 90 min bloque aussi
l'atelier). En cas de doute technique, on laisse passer plutôt que de perdre le client.

**Créneaux sous réserve**
Quand l'agenda n'est pas rattaché, `check_availability` renvoie `tentative: true` et l'agent
dit « sous réserve de confirmation par le garage » au lieu d'annoncer des créneaux fermes.

Horaires : `app/utils/business_hours.py` (`is_open_at`, `next_opening_fr`,
`describe_hours_fr`). Sans horaires exploitables, on considère le garage **fermé** — mieux
vaut prendre un message à tort que promettre un transfert qui n'aboutira pas.

Prompts mis à jour (`garage_mecanique_v1.txt`), outil déclaré côté Vapi.
Simulateur : `--scenario voiture-prete`, `--scenario creneau-pris`, option `--ferme`.
**Suite complète : 71 tests verts.**

### Reste à traiter sur les cas d'usage
- **Congés — décision prise le 14/08/2026** : pas de colonne `closures`, pas de migration.
  Le garage bloque ses congés **dans son propre agenda** (période indisponible Cal.com), qui
  reste la seule source de vérité. À développer : une feature « garage en vacances » — quand
  l'agenda ne renvoie aucun créneau sur la fenêtre courante, élargir la recherche, annoncer
  la fermeture et proposer les premiers créneaux disponibles à la réouverture, au lieu de
  répondre « aucune disponibilité ».
  ⚠️ Cette feature suppose l'agenda réellement rattaché : sans lui, les créneaux de repli
  ignorent les congés (ils sont annoncés « sous réserve », ce qui limite la casse).
- Démarchage téléphonique, clients non francophones, devis détaillé : à arbitrer avec les
  premiers testeurs plutôt qu'à deviner maintenant.

## ✅ Étape 13 — Déploiement Cloud Run : PRÊT (14/08/2026) — bloc D

Tout est écrit et vérifiable ; **le déploiement effectif attend un moyen de paiement**
(Google Cloud exige une carte pour activer la facturation, même si l'usage reste dans le
palier gratuit — voir `docs/DEPLOIEMENT.md`).

**Dépendances scindées en trois fichiers.** `requirements.txt` ne contenait que 11 des
40 paquets réellement nécessaires au backend : streamlit, pandas, ipython, mypy et les
autres partaient dans l'image. Chaque paquet en trop alourdit le démarrage à froid, donc
la latence du premier appel (objectif < 800 ms, étape 12).

    requirements.txt             → exécution du backend (11 paquets, vérifiés par grep des imports)
    requirements-dev.txt         → tests, lint, scripts
    requirements-dashboard.txt   → streamlit, plotly, pandas

⚠️ Ton venv actuel a déjà tout : rien ne casse. Sur une machine neuve, installer
`requirements-dev.txt` **et** `requirements-dashboard.txt`.

**`Dockerfile`** — image en deux étages (les outils de compilation ne partent pas en
production), utilisateur non root, `PORT` lu à l'exécution (Cloud Run l'impose et peut le
changer), un seul worker (Cloud Run monte en charge en ajoutant des instances).

**`.dockerignore`** — exclut `.env` en premier lieu : un fichier de secrets copié dans une
image reste lisible par quiconque la télécharge.

**`.github/workflows/ci.yml`** — tests + construction de l'image + démarrage réel du
conteneur vérifié sur `/health`, à chaque push. `PROVIDER_MODE=fake` : la CI n'envoie aucun
SMS et ne consomme aucun crédit. Sans secrets Supabase configurés, les tests d'intégration
se désactivent d'eux-mêmes et la CI reste verte.

**`.github/workflows/deploy.yml`** — déclenchement **manuel** volontairement : un déploiement
automatique enverrait en production du code jamais essayé en conditions réelles, sur un
service qui décroche le téléphone. Authentification par Workload Identity Federation (aucune
clé JSON téléchargée). Vérifie `/health` après déploiement et **restaure la version
précédente** en cas d'échec.

**`docs/DEPLOIEMENT.md`** — procédure complète : projet GCP, Artifact Registry, secrets,
fédération d'identité, bascule des URL.

Vérifié sans Docker (non installé sur ce poste) : l'application démarre bien avec
`APP_ENV=production` et le port injecté par variable ; `/health` répond 200 et `/docs`
renvoie 404 (documentation désactivée en production). Le `docker build` lui-même n'a **pas**
pu être essayé localement — c'est la CI qui le validera au premier push.

Ajouté au démarrage : un log d'erreur si `PROVIDER_MODE=fake` est actif en production
(sinon aucun SMS ne partirait réellement, sans que rien ne le signale).

### Après le premier déploiement — 3 URL à reporter
1. Vapi : webhooks et outils → `<URL>/api/webhooks/vapi`, `<URL>/api/tools/*`
2. `APP_BASE_URL` dans les variables Cloud Run
3. Google OAuth : URI de redirection → `<URL>/auth/google/callback`

## ✅ Rappels de rendez-vous J-1 et H-2 — bloc C (14/08/2026)

`reminder_24h_sent` et `reminder_2h_sent` existaient depuis la création du schéma **sans
que rien ne les remplisse** : aucun rappel n'a jamais été envoyé. C'est pourtant le
meilleur rapport effort/valeur du produit — un no-show coûte au garage un créneau
d'atelier non facturable, et c'est l'argument commercial le plus concret à présenter.

    venv\Scripts\python.exe scripts/send_reminders.py --dry-run   # liste sans envoyer
    venv\Scripts\python.exe scripts/send_reminders.py             # envoie

En production : Cloud Scheduler appelle `POST /internal/reminders/run` toutes les heures
(3 tâches gratuites, il en faut une). Configuration dans `docs/DEPLOIEMENT.md` étape 7.

### Trois garde-fous, et pourquoi
1. **Idempotence par réservation optimiste** — le drapeau est posé *avant* l'envoi, sous
   condition qu'il soit encore à `false`. Si deux exécutions se chevauchent, une seule
   gagne la ligne ; si l'envoi échoue, le drapeau est relâché pour retenter au passage
   suivant. Recevoir deux fois le même rappel décrédibilise l'agent auprès du client.
2. **Heures décentes** — aucun SMS entre 20h et 8h. Réveiller un client à 3h annule tout
   le bénéfice du rappel.
3. **Rien** sur un RDV passé, annulé, ou sans numéro exploitable (marqué quand même, sinon
   le service réessaierait indéfiniment à chaque passage).

Le message contient prénom, garage, date en français, prestation, et **le numéro pour
annuler** : un client qui peut annuler facilement libère le créneau au lieu de ne pas venir.

Sécurité : `/internal/*` est protégée par `CRON_SECRET` (comparaison en temps constant),
refusée en production si le secret n'est pas configuré — une route qui envoie des SMS en
masse et que n'importe qui peut déclencher est une porte ouverte à la facture.

Fichiers : `app/services/reminder_service.py`, `app/api/internal.py`,
`scripts/send_reminders.py`, `tests/integration/test_reminders.py` (13 tests).
**Suite complète : 84 tests verts.**

⚠️ Corrigé au passage : le journal du mode simulé tronquait les messages à 80 caractères,
ce qui masquait leur contenu réel aux tests. Un faux journal cache les défauts qu'il est
censé révéler — même principe que la fidélité du simulateur Cal.com.

## ⏳ Étape 12 — Optimisation (À FAIRE)