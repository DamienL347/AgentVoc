# Déploiement — Google Cloud Run

Objectif : remplacer ngrok par une **URL publique fixe**. Aujourd'hui, l'URL ngrok
change à chaque redémarrage, ce qui oblige à reconfigurer Vapi et `APP_BASE_URL` à
chaque fois — impensable avec un client réel qui peut appeler à tout moment.

---

## ⚠️ Ce que ça coûte, honnêtement

Le service lui-même tient dans le **palier gratuit** de Cloud Run (2 millions de
requêtes par mois ; quelques centaines d'appels n'en consomment qu'une fraction).
Artifact Registry offre 0,5 Go, une image de ce backend en pèse environ 0,2.

**Mais Google Cloud exige une carte bancaire pour activer la facturation**, même si
la consommation reste nulle. Les nouveaux comptes reçoivent généralement 300 $ de
crédits offerts, à vérifier au moment de l'inscription.

Autrement dit : le déploiement ne coûte quasiment rien, mais il ne peut pas se faire
sans moyen de paiement enregistré. Tout ce qui suit est prêt et peut attendre.

---

## Étape 1 — Le projet Google Cloud

```bash
gcloud auth login
gcloud projects create agentlumy-prod --name="AgentLumy"
gcloud config set project agentlumy-prod
```

Activer la facturation depuis la console (`Facturation` → associer un compte), puis
les services nécessaires :

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```

## Étape 2 — Le dépôt d'images

```bash
gcloud artifacts repositories create agentlumy --repository-format=docker --location=europe-west1 --description="Images AgentLumy"
```

`europe-west1` (Belgique) est la région la plus proche des clients français : chaque
aller-retour réseau compte dans la latence perçue au téléphone.

## Étape 3 — Les secrets

Aucun secret ne doit se retrouver dans l'image ni dans le dépôt Git. Ils vivent dans
Secret Manager et Cloud Run les injecte comme variables d'environnement au démarrage.

À créer, un par un (les noms doivent correspondre exactement à ceux attendus par
`.github/workflows/deploy.yml`) :

```bash
printf '%s' 'VALEUR' | gcloud secrets create supabase-url --data-file=-
```

| Secret | Source |
|---|---|
| `supabase-url` | Supabase → Project Settings → API |
| `supabase-service-role-key` | idem (⚠️ contourne le RLS, ne jamais exposer côté client) |
| `supabase-anon-key` | idem |
| `vapi-private-key` | Vapi → API Keys |
| `vapi-webhook-secret` | Vapi → Webhooks (**obligatoire en production**) |
| `twilio-account-sid` | Twilio Console |
| `twilio-auth-token` | Twilio Console |
| `twilio-phone-number` | numéro FR au format E.164 |
| `calcom-api-key` | Cal.com → Settings → Developer |
| `resend-api-key` | Resend → API Keys |
| `cartesia-api-key` | Cartesia |
| `deepgram-api-key` | Deepgram |

> `VAPI_WEBHOOK_SECRET` n'est pas optionnel : le service est exposé publiquement
> (Vapi appelle les webhooks sans identifiants Google). C'est la signature HMAC qui
> empêche n'importe qui de déclencher des appels d'outils. Sans ce secret,
> `app/api/security.py` refuse toutes les requêtes en production — c'est voulu.

## Étape 4 — Autoriser GitHub à déployer

On utilise Workload Identity Federation : GitHub prouve son identité à Google sans
qu'aucune clé ne soit téléchargée. Une clé de compte de service stockée dans un
secret GitHub est un secret permanent qui finit toujours par fuiter.

```bash
# Compte de service utilisé par le déploiement
gcloud iam service-accounts create github-deploy --display-name="Déploiement GitHub"

PROJET=$(gcloud config get-value project)
COMPTE="github-deploy@${PROJET}.iam.gserviceaccount.com"

for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJET" --member="serviceAccount:${COMPTE}" --role="$role"
done

# Fédération d'identité
gcloud iam workload-identity-pools create github --location=global --display-name="GitHub"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='DamienL347/AgentVoc'"
```

L'`attribute-condition` est essentielle : sans elle, **n'importe quel dépôt GitHub**
pourrait s'authentifier auprès de ton projet.

Puis lier le dépôt au compte de service :

```bash
NUM=$(gcloud projects describe "$PROJET" --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding "$COMPTE" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${NUM}/locations/global/workloadIdentityPools/github/attribute.repository/DamienL347/AgentVoc"
```

Enfin, dans GitHub → Settings → Secrets and variables → Actions :

| Secret GitHub | Valeur |
|---|---|
| `GCP_PROJECT_ID` | l'identifiant du projet |
| `GCP_SERVICE_ACCOUNT` | `github-deploy@<projet>.iam.gserviceaccount.com` |
| `GCP_WIF_PROVIDER` | `projects/<NUM>/locations/global/workloadIdentityPools/github/providers/github-provider` |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` | pour que la CI puisse lancer les tests d'intégration |

## Étape 5 — Déployer

Le déploiement est **manuel** pour l'instant : GitHub → Actions → « Déploiement
Cloud Run » → Run workflow. Un déploiement automatique à chaque push enverrait en
production du code jamais essayé en conditions réelles ; à activer une fois la
mise en production rodée (bloc `push` commenté dans `deploy.yml`).

Le workflow vérifie `/health` après déploiement et **restaure automatiquement la
version précédente** si le service ne répond pas.

## Étape 6 — Après le premier déploiement

L'URL obtenue est stable (`https://voice-agent-garage-api-XXXX.europe-west1.run.app`).
Trois endroits à mettre à jour, sans quoi les appels continueront de pointer vers ngrok :

1. **Vapi** → l'URL des webhooks et des outils : `<URL>/api/webhooks/vapi`, `<URL>/api/tools/*`
2. **`APP_BASE_URL`** → variable d'environnement Cloud Run (elle sert à générer les
   URL d'outils lors de la création des assistants)
3. **Google OAuth** → URI de redirection autorisée : `<URL>/auth/google/callback`

Puis vérifier :

```bash
curl https://<URL>/health          # {"status":"ok"}
curl https://<URL>/docs            # 404 attendu : la doc est désactivée en production
```

---

## Étape 7 — Les rappels de rendez-vous (Cloud Scheduler)

Les rappels J-1 et H-2 sont déclenchés par un appel HTTP à
`POST /internal/reminders/run`. Cloud Scheduler offre **3 tâches gratuites**, il en
faut une seule.

D'abord le secret partagé qui protège la route (elle envoie des SMS : sans
protection, n'importe qui pourrait la déclencher en boucle) :

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
printf '%s' 'LA_VALEUR_GENEREE' | gcloud secrets create cron-secret --data-file=-
```

Ajouter `CRON_SECRET=cron-secret:latest` à la liste `--set-secrets` de
`deploy.yml`, puis créer la tâche :

```bash
gcloud scheduler jobs create http rappels-rdv \
  --location=europe-west1 \
  --schedule="0 9-19 * * *" \
  --time-zone="Europe/Paris" \
  --uri="https://<URL_CLOUD_RUN>/internal/reminders/run" \
  --http-method=POST \
  --headers="x-cron-secret=LA_VALEUR_GENEREE" \
  --attempt-deadline=120s
```

Toutes les heures entre 9h et 19h : le service refuse de toute façon d'envoyer
hors de la plage 8h-20h, mais éviter de le réveiller la nuit économise des
démarrages à froid inutiles.

Une exécution manquée n'est pas grave : la fenêtre de recherche est large et le
drapeau en base empêche les doublons, donc le passage suivant rattrape.

Vérification :

```bash
gcloud scheduler jobs run rappels-rdv --location=europe-west1
gcloud scheduler jobs describe rappels-rdv --location=europe-west1
```

En local, avant le déploiement :

```bash
venv\Scripts\python.exe scripts/send_reminders.py --dry-run   # liste sans envoyer
venv\Scripts\python.exe scripts/send_reminders.py             # envoie
```

---

## Vérifier l'image en local (facultatif, nécessite Docker)

```bash
docker build -t agentlumy-api .
docker run --rm -p 8080:8080 --env-file .env agentlumy-api
curl http://localhost:8080/health
```

## Choix techniques et leurs raisons

| Choix | Pourquoi |
|---|---|
| Image en deux étages | Les outils de compilation restent hors de l'image finale : plus légère, démarrage à froid plus rapide, moins de surface exposée |
| Utilisateur non root | Un processus compromis n'a aucun droit sur le système de fichiers |
| `--min-instances 0` | Aucun coût quand personne n'appelle. Contrepartie : un démarrage à froid sur le premier appel — à réévaluer avec un vrai client (voir étape 12) |
| `--max-instances 5` | Garde-fou : une boucle d'appels ne peut pas faire exploser la facture |
| Un seul worker | Cloud Run monte en charge en ajoutant des instances, pas des processus |
| `PORT` lu à l'exécution | Cloud Run impose le port et peut le changer |
| Déploiement manuel | Une mise en production non surveillée sur un service qui décroche le téléphone est un risque inutile |

## Coûts mensuels estimés (3 clients)

| Poste | Coût |
|---|---|
| Cloud Run | ~0 € (palier gratuit) |
| Artifact Registry | ~0 € (< 0,5 Go) |
| Secret Manager | ~0,10 € |
| Cloud Scheduler | 0 € (3 tâches gratuites — servira aux rappels J-1) |

⚠️ Ce tableau ne couvre que l'hébergement. Vapi, Twilio, Cal.com, Cartesia et
Supabase Pro restent les vrais postes de dépense — à recalculer avec la mesure du
coût réel par appel (étape 12).
