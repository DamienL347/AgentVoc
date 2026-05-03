# 🚗 Voice Agent Garage — Agent IA Vocal pour Garagistes & Dépanneurs

> Agent IA vocal autonome capable de répondre aux appels entrants, comprendre les demandes des clients, proposer et réserver des rendez-vous, et synchroniser automatiquement avec un agenda. Architecture multi-tenant scalable pour plusieurs garages.

---

## 🎯 Cibles & Périmètre fonctionnel

**Cibles :** Garagistes (mécanique générale) + Dépanneurs/Remorquage

**Cas d'usage gérés (V1) :**
- ✅ Prise de RDV pour intervention planifiée (révision, réparation, contrôle technique)
- ✅ Demande d'information basique (horaires, services, adresse)
- ✅ Demande de devis simple (redirection vers RDV)
- ✅ Modification ou annulation de RDV existant
- ✅ Dépannage non urgent (qualification + RDV diagnostic)
- ✅ Détection de mécontentement → transfert humain
- ✅ Détection d'urgence (escalation path 24/7)

---

## 🛠️ Stack Technique

| Brique | Outil | Rôle |
|---|---|---|
| **LLM** | Claude 3.5 Haiku | Cerveau conversationnel |
| **Voix (STT/Orchestration)** | Vapi + Deepgram | Transcription temps réel |
| **Voix (TTS)** | Cartesia Sonic | Synthèse vocale FR |
| **Téléphonie** | Twilio | Numéros entrants |
| **Backend** | Python FastAPI | Logique métier |
| **Hébergement** | Railway | Déploiement backend |
| **Base de données** | Supabase (PostgreSQL) | Stockage multi-tenant |
| **Agenda** | Cal.com + Google Calendar | Réservation & sync |
| **SMS** | Twilio | Alertes/transferts |
| **Email** | Resend | Confirmations RDV |
| **Dashboard** | Metabase | Analytics interne |
| **Workflow annexes** | n8n (self-hosted) | Notifications/intégrations |

---

## ✅ Checklist de démarrage

### 🔐 Comptes à créer (Étape 3)

- [ ] **Anthropic** — https://console.anthropic.com (charger 10$ de crédits)
- [ ] **Vapi** — https://vapi.ai (récupérer Public + Private Keys)
- [ ] **Cartesia** — https://cartesia.ai (récupérer API Key)
- [ ] **Twilio** — https://www.twilio.com (acheter 1 numéro FR pour tests)
- [ ] **Supabase** — https://supabase.com (créer projet, récupérer URL + keys)
- [ ] **Cal.com** — https://cal.com (compte cloud pour V1)
- [ ] **Railway** — https://railway.app (login GitHub)
- [ ] **GitHub** — créer repo privé `voice-agent-garage`
- [ ] **Resend** — https://resend.com (API key)
- [ ] **Google Cloud** — https://console.cloud.google.com (Calendar API + OAuth)

### 💻 Outils locaux

- [ ] Python 3.11+ installé (`python --version`)
- [ ] Git configuré (`git config --global user.name`)
- [ ] VS Code ou Cursor installé
- [ ] Docker Desktop installé
- [ ] Postman ou Insomnia installé
- [ ] DBeaver ou TablePlus installé (client SQL)

### 🚀 Premier setup

```bash
# 1. Cloner le repo
git clone https://github.com/<your-username>/voice-agent-garage.git
cd voice-agent-garage

# 2. Créer l'environnement Python
python -m venv venv
source venv/bin/activate  # macOS/Linux
# ou
venv\Scripts\activate  # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Copier .env.example en .env et remplir les clés
cp .env.example .env
# Édite .env avec tes clés API

# 5. Vérifier la config
python -m app.config

# 6. Lancer le serveur en local
uvicorn app.main:app --reload --port 8000
```

---

## 📁 Structure du projet

```
voice-agent-garage/
├── app/
│   ├── api/              # Routes FastAPI (webhooks Vapi, tools, admin)
│   ├── core/             # Logique métier (call handler, booking, urgency)
│   ├── integrations/     # Connecteurs externes (Vapi, Cal.com, etc.)
│   ├── models/           # Modèles Pydantic
│   ├── db/               # Couche données (Supabase + repositories)
│   ├── prompts/          # System prompts versionnés
│   ├── config.py         # Configuration Pydantic Settings
│   └── main.py           # Entry point FastAPI
├── tests/                # Tests unitaires + intégration
├── scripts/              # Scripts utilitaires (SQL, seeds, deploy)
├── docs/                 # Documentation technique
├── .env.example
├── .gitignore
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 📊 Modèle de données (résumé)

### Tables principales

- **garages** — Clients de la plateforme (multi-tenant)
- **calls** — Historique de tous les appels reçus
- **appointments** — RDV pris/modifiés/annulés
- **clients** — Clients finaux des garages
- **vehicles** — Véhicules associés aux clients
- **interventions** — Catalogue des types d'interventions par garage

Schéma SQL complet : voir `scripts/setup_supabase.sql` (Étape 4).

---

## 🗺️ Roadmap

### ✅ Phase 1 — Fondations
- [x] Étape 1 : Cadrage fonctionnel (cible, cas d'usage, modèle de données)
- [x] Étape 2 : Choix du stack technique
- [x] Étape 3 : Préparation environnement de travail

### 🔄 Phase 2 — Construction MVP
- [ ] Étape 4 : Schéma BDD Supabase + repositories
- [ ] Étape 5 : System prompt de l'agent + scénarios
- [ ] Étape 6 : Configuration Vapi + intégration Claude
- [ ] Étape 7 : Backend FastAPI (webhooks, tools)
- [ ] Étape 8 : Intégration agenda (Cal.com + Google Calendar)
- [ ] Étape 9 : Tests end-to-end en conditions réelles

### 📦 Phase 3 — Industrialisation
- [ ] Étape 10 : Architecture multi-tenant complète
- [ ] Étape 11 : Dashboard de monitoring
- [ ] Étape 12 : Optimisation latence + coûts

### 💼 Phase 4 — Commercialisation
- [ ] Étape 13 : Pricing & offre commerciale
- [ ] Étape 14 : Acquisition premiers clients
- [ ] Étape 15 : Onboarding & SLA

---

## 💰 Estimation des coûts mensuels

Pour 3 clients actifs (~500 minutes/client/mois) :

| Poste | Coût mensuel |
|---|---|
| Vapi | ~75€ |
| Twilio (numéros + SMS) | ~15€ |
| Anthropic (Claude Haiku) | ~10€ |
| Cartesia TTS | ~20€ |
| Supabase | 0€ (tier gratuit) |
| Cal.com Cloud | ~15€ |
| Railway | ~10€ |
| Resend | 0€ (tier gratuit) |
| **TOTAL** | **~145€/mois** |

**Marge nette** avec 3 clients à 400€/mois : **~85%**.

---

## 🔐 Sécurité & Conformité

- ✅ Toutes les clés API en variables d'environnement (jamais commit)
- ✅ Webhooks Vapi vérifiés via signature HMAC
- ✅ RGPD : transcriptions chiffrées, durée de rétention configurable
- ✅ Supabase : Row Level Security (RLS) activée pour isolation multi-tenant
- ✅ HTTPS obligatoire en production

---

## 📝 Licence

Projet privé. Usage commercial réservé au propriétaire.

---

## 👤 Contact

Projet conçu et développé par [Ton Nom].
