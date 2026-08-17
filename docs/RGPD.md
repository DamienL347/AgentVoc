# RGPD — AgentLumy

> ⚠️ **Ce document est une base de travail technique, pas un avis juridique.**
> Il décrit ce que le logiciel fait réellement et ce qu'il reste à décider.
> Les documents contractuels (politique de confidentialité, contrat de
> sous-traitance) doivent être **relus par un juriste** avant d'être remis à un
> client. Je ne suis pas juriste ; ce qui est affirmé ici sur le plan technique
> est vérifiable dans le code, ce qui relève du droit doit être validé.

---

## 1. Pourquoi le sujet est sérieux ici

Le produit **enregistre et transcrit des conversations téléphoniques**. Ce sont des
données personnelles, et l'enregistrement de la voix est une donnée particulièrement
sensible aux yeux des personnes concernées. Trois conséquences :

1. l'appelant doit être **informé dès le décrochage** ;
2. les données ne peuvent pas être conservées indéfiniment ;
3. plusieurs sous-traitants **hors Union européenne** traitent ces données.

## 2. Qui est responsable de quoi

| Rôle | Qui | Ce que ça implique |
|---|---|---|
| **Responsable de traitement** | **Le garage** | C'est lui qui décide de faire répondre ses appels par un agent, et qui répond aux personnes concernées |
| **Sous-traitant** | **AgentLumy** | Traite les données sur instruction du garage, et uniquement pour lui |
| **Sous-traitants ultérieurs** | Vapi, Deepgram, Anthropic, Cartesia, Twilio, Supabase, Resend | Doivent être portés à la connaissance du garage et autorisés par lui |

⚠️ **Conséquence contractuelle** : il faut un **contrat de sous-traitance (DPA)** entre
AgentLumy et chaque garage — c'est une obligation de l'article 28, et les garages
sérieux le demanderont. C'est un document commercial autant que juridique : ne pas
l'avoir bloquera des signatures.

## 3. Ce que le logiciel fait aujourd'hui — vérifiable

### Information de l'appelant ✅
La phrase d'accueil contient l'information, dès le décrochage :

> « Bonjour, je suis Léa, l'assistante vocale de Garage Martin. **Cet appel peut être
> enregistré.** Comment puis-je vous aider ? »

Généré par `app/prompts/system_prompt.py`, vérifié par un test sur les 4 types de garage
(`tests/unit/test_prompt_coherence.py`). L'enregistrement est pilotable par garage via
`ENABLE_CALL_RECORDING`.

### Durées de conservation ✅ (implémentées le 17/08/2026)

| Donnée | Durée | Traitement à l'échéance |
|---|---|---|
| Enregistrement audio | 30 j | Supprimé (`recording_url` → NULL) |
| Transcription | 90 j | Supprimée |
| N° appelant, résumé | 365 j | **Anonymisés** |
| Contenu SMS/emails | 365 j | Anonymisé (canal et statut conservés comme preuve d'envoi) |
| Fiche client sans contact | 3 ans | Supprimée |

**Choix : anonymiser plutôt que supprimer.** Les métadonnées non identifiantes (durée,
statut, type de demande) restent en base pour les statistiques du dashboard. Supprimer
les lignes ferait perdre l'historique des KPI sans bénéfice supplémentaire côté
conformité.

Durées configurables dans `.env` (`RETENTION_*_DAYS`) — à **valider avec chaque garage**,
qui est le responsable de traitement.

    venv\Scripts\python.exe scripts/rgpd.py inventaire        # ce qui est détenu
    venv\Scripts\python.exe scripts/rgpd.py purge --dry-run   # sans rien modifier
    venv\Scripts\python.exe scripts/rgpd.py purge

En production : `POST /internal/retention/run`, une fois par jour via Cloud Scheduler.

### Droit à l'effacement (article 17) ✅

    venv\Scripts\python.exe scripts/rgpd.py effacer +33612345678 --garage <id> --dry-run

**Cloisonné par garage, volontairement** : un même numéro peut être client de deux
garages concurrents, et un garage n'a aucun droit sur les données détenues par un autre.
`--tous-garages` existe pour une demande adressée à AgentLumy en tant que plateforme.

### Cloisonnement des données ✅
Row Level Security active sur les 10 tables, et un test vérifie qu'un garage ne peut ni
lire ni modifier les rendez-vous d'un autre (`test_cas4_cloisonnement_entre_garages`).

## 4. Ce qui reste à faire — par ordre d'urgence

### 4.1 Contrat de sous-traitance (DPA) — bloquant commercial
À rédiger et faire relire. Doit contenir : objet et durée du traitement, nature des
données, obligations de sécurité, liste des sous-traitants ultérieurs, sort des données
en fin de contrat, assistance en cas de demande d'une personne concernée.

### 4.2 Transferts hors UE — point à ne pas négliger
Plusieurs sous-traitants sont **américains** : Vapi, Deepgram, Anthropic, Cartesia,
Twilio, Resend. Les conversations de clients français y transitent.

À vérifier pour chacun : adhésion au *Data Privacy Framework* ou clauses contractuelles
types, et localisation de l'hébergement. Supabase permet de choisir une région UE — **à
confirmer pour le projet actuel**. C'est le point sur lequel un garage prudent (ou son
comptable) posera des questions.

### 4.3 Politique de confidentialité
À publier sur agentlumy.com et à fournir aux garages pour leurs propres clients.
Doit indiquer : identité du responsable, finalités, base légale, durées (§3 ci-dessus),
destinataires, transferts hors UE, droits et modalités d'exercice.

### 4.4 Registre des traitements
Obligation de l'article 30. `scripts/rgpd.py inventaire` fournit les volumes réels à y
inscrire.

### 4.5 Base légale de l'enregistrement — à trancher
Deux options, à arbitrer avec un juriste :
- **intérêt légitime** (amélioration du service), avec information claire — c'est
  l'hypothèse actuelle du produit ;
- **consentement**, plus contraignant : il faudrait une réponse explicite de l'appelant
  avant d'enregistrer, et gérer le refus.

Une piste intermédiaire si l'enregistrement n'est pas indispensable : désactiver
`ENABLE_CALL_RECORDING` et ne conserver que la transcription, voire seulement le résumé.
**Moins de données détenues, moins de risque** — et c'est un argument commercial auprès
d'un garagiste soucieux de ses clients.

### 4.6 Violation de données
Obligation de notifier la CNIL sous 72 h. À préparer : qui constate, qui notifie, quel
canal. Un incident n'est pas le bon moment pour improviser cette chaîne.

## 5. Sous-traitants ultérieurs — à annexer au DPA

| Fournisseur | Rôle | Données traitées |
|---|---|---|
| Vapi | Orchestration de l'appel | Audio, transcription, métadonnées |
| Deepgram | Transcription (STT) | Audio de l'appel |
| Anthropic | Compréhension (LLM) | Transcription du dialogue |
| Cartesia | Synthèse vocale (TTS) | Texte prononcé par l'agent |
| Twilio | Téléphonie et SMS | N° appelant, contenu des SMS |
| Supabase | Base de données | Toutes les données du produit |
| Resend | Emails | Email et nom du client |
| Google Cloud Run | Hébergement du backend | Données en transit |
| Cal.com | Agenda | Nom, téléphone, email, motif du RDV |

---

*Rédigé le 17/08/2026. §3 décrit du code vérifiable ; §4 liste des décisions à prendre.*
