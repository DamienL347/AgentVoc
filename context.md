# 🚗 CONTEXT.MD — AgentVoc (Voice Agent Garage)
> À coller en début de nouvelle conversation pour reprendre le projet

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

## ⏳ Étape 11 — Dashboard monitoring (À FAIRE)