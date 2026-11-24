#!/usr/bin/env bash
# Deploys Learning Coach to Google Cloud Run: the Chainlit app (public) and the two MCP servers (private).
#
#   deploy/gcp/deploy.sh                 # uses your current gcloud project, region europe-west1
#   PROJECT_ID=my-proj REGION=europe-west2 deploy/gcp/deploy.sh
#
# Safe to re-run: every step creates what is missing and updates what exists.
# Secrets are read from learning_coach/.env and stored in Secret Manager; they never go into an image.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/learning_coach/.env}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-europe-west1}"        # close to Supabase eu-west-1 (Ireland)
AR_REPO="${AR_REPO:-learning-coach}"
TAG="${TAG:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo latest)-$(date +%Y%m%d%H%M%S)}"

APP_SA="lc-app"
MCP_SA="lc-mcp"
SECRETS=(DATABASE_URL CHAINLIT_AUTH_SECRET OLLAMA_API_KEY GROQ_API_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY)

[[ -n "$PROJECT_ID" ]] || { echo "No GCP project: set PROJECT_ID or run 'gcloud config set project <id>'"; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE"; exit 1; }

# Value of KEY in the .env file (last occurrence, surrounding quotes removed). The file is never sourced.
env_val() {
  local v
  v="$(grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true)"
  v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
  printf '%s' "$v"
}

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

DB_URL="$(env_val DATABASE_URL)"
if [[ -z "$DB_URL" || "$DB_URL" == *YOUR-DATABASE-PASSWORD* || "$DB_URL" == *localhost* ]]; then
  echo "DATABASE_URL in $ENV_FILE is missing, still has the placeholder password, or points at localhost."; exit 1
fi
[[ -n "$(env_val CHAINLIT_AUTH_SECRET)" ]] || { echo "CHAINLIT_AUTH_SECRET is empty (openssl rand -hex 32)"; exit 1; }
[[ "$(env_val OLLAMA_BASE_URL)" != *localhost* ]] || { echo "OLLAMA_BASE_URL points at localhost; use https://ollama.com"; exit 1; }
[[ -n "$(env_val OLLAMA_API_KEY)" ]] || { echo "OLLAMA_API_KEY is empty (https://ollama.com/settings/keys)"; exit 1; }

IMAGE_PREFIX="$REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPO"
gc() { gcloud --project "$PROJECT_ID" --quiet "$@"; }

step "Project $PROJECT_ID, region $REGION, tag $TAG"

step "Enabling APIs"
gc services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com iam.googleapis.com

step "Artifact Registry repo"
gc artifacts repositories describe "$AR_REPO" --location "$REGION" >/dev/null 2>&1 \
  || gc artifacts repositories create "$AR_REPO" --repository-format docker --location "$REGION"

step "Service accounts"
for sa in "$APP_SA" "$MCP_SA"; do
  gc iam service-accounts describe "$sa@$PROJECT_ID.iam.gserviceaccount.com" >/dev/null 2>&1 \
    || gc iam service-accounts create "$sa" --display-name "Learning Coach $sa"
done
APP_SA_EMAIL="$APP_SA@$PROJECT_ID.iam.gserviceaccount.com"
MCP_SA_EMAIL="$MCP_SA@$PROJECT_ID.iam.gserviceaccount.com"

step "Secrets (from $ENV_FILE)"
SET_SECRETS=()
for name in "${SECRETS[@]}"; do
  val="$(env_val "$name")"
  [[ -n "$val" ]] || { echo "  $name: empty, skipped"; continue; }
  if ! gc secrets describe "$name" >/dev/null 2>&1; then
    gc secrets create "$name" --replication-policy automatic >/dev/null
  fi
  current="$(gc secrets versions access latest --secret "$name" 2>/dev/null || true)"
  if [[ "$current" != "$val" ]]; then
    printf '%s' "$val" | gc secrets versions add "$name" --data-file=- >/dev/null
    echo "  $name: new version"
  else
    echo "  $name: unchanged"
  fi
  gc secrets add-iam-policy-binding "$name" --member "serviceAccount:$APP_SA_EMAIL" \
    --role roles/secretmanager.secretAccessor >/dev/null
  SET_SECRETS+=("$name=$name:latest")
done

step "Building images with Cloud Build"
gc builds submit "$ROOT" --config "$ROOT/deploy/gcp/cloudbuild.yaml" \
  --substitutions "_REPO=$IMAGE_PREFIX,_TAG=$TAG"

# Private MCP server: only identities with run.invoker (the app's service account) can call it.
deploy_mcp() {
  local name="$1" port="$2"
  gc run deploy "$name" --region "$REGION" --image "$IMAGE_PREFIX/$name:$TAG" \
    --service-account "$MCP_SA_EMAIL" --no-allow-unauthenticated --port "$port" \
    --cpu 1 --memory 512Mi --min-instances 0 --max-instances 1 --timeout 3600 >/dev/null
  gc run services add-iam-policy-binding "$name" --region "$REGION" \
    --member "serviceAccount:$APP_SA_EMAIL" --role roles/run.invoker >/dev/null
  gc run services describe "$name" --region "$REGION" --format 'value(status.url)'
}

step "Deploying MCP servers (private)"
FILE_URL="$(deploy_mcp file-server-mcp 8001)"
MEMORY_URL="$(deploy_mcp memory-server-mcp 8002)"
echo "  file-server-mcp:   $FILE_URL"
echo "  memory-server-mcp: $MEMORY_URL"

step "Deploying app (public)"
ENV_PAIRS=()
# Adds KEY=VALUE, skipping empty values so the app's own defaults apply.
add_env() { [[ -n "$2" ]] && ENV_PAIRS+=("$1=$2") || true; }
for key in LLM_PROVIDER FALLBACK_LLM_PROVIDER OLLAMA_BASE_URL OLLAMA_MODEL GROQ_MODEL LANGFUSE_HOST; do
  add_env "$key" "$(env_val "$key")"
done
add_env DAILY_GOAL_LIMIT "${DAILY_GOAL_LIMIT:-$(env_val DAILY_GOAL_LIMIT)}"
add_env MCP_FILESYSTEM_URL "$FILE_URL/mcp"
add_env MCP_MEMORY_URL "$MEMORY_URL/mcp"
add_env MCP_AUTH google
# Not deployed: the app runs the quiz in-process. Settings still require these keys.
add_env USE_A2A_QUIZ false;  add_env QUIZ_SERVICE_URL http://unused:9001
add_env USE_STUDY_BUDDY false; add_env STUDY_BUDDY_URL http://unused:9002
add_env CHECKPOINT_DB data/checkpoints.db
add_env NOTES_PATH study_materials/sample_notes
add_env LOG_LEVEL INFO
# '^|^' makes '|' the separator, so values may contain commas.
ENV_VARS="^|^$(IFS='|'; echo "${ENV_PAIRS[*]}")"

# Chainlit keeps each chat on a websocket and in process memory, so: one instance, session affinity,
# and the longest request timeout (60 min) so a study session is not cut off.
gc run deploy app --region "$REGION" --image "$IMAGE_PREFIX/app:$TAG" \
  --service-account "$APP_SA_EMAIL" --allow-unauthenticated --port 8000 \
  --cpu 1 --memory 2Gi --min-instances 0 --max-instances 1 --concurrency 80 \
  --timeout 3600 --session-affinity --cpu-boost \
  --set-env-vars "$ENV_VARS" \
  --set-secrets "$(IFS=,; echo "${SET_SECRETS[*]}")"

APP_URL="$(gc run services describe app --region "$REGION" --format 'value(status.url)')"
step "Done: $APP_URL"
