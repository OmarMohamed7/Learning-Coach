# Deploying to Google Cloud Run

```
Browser ──HTTPS──▶ app (Chainlit, public) ──ID token──▶ file-server-mcp (private)
                       │                    └─ID token──▶ memory-server-mcp (private)
                       ├──▶ Supabase Postgres (session pooler, eu-west-1)
                       └──▶ Ollama Cloud (Groq fallback)
```

## One-time setup

1. `gcloud auth login` and `gcloud config set project <your-project-id>` (billing must be enabled).
2. In `learning_coach/.env`, set:
   - `DATABASE_URL`: the Supabase session pooler URL with your real password.
   - `CHAINLIT_AUTH_SECRET`: generate it with `openssl rand -hex 32`.
   - `OLLAMA_API_KEY`: from https://ollama.com/settings/keys (`OLLAMA_BASE_URL=https://ollama.com`). `GROQ_API_KEY` is the fallback.

## Deploy (and every redeploy)

```bash
deploy/gcp/deploy.sh
# optional: PROJECT_ID=... REGION=europe-west2 DAILY_GOAL_LIMIT=10 deploy/gcp/deploy.sh
```

It prints the app URL at the end. Re-running builds new images and rolls out a new revision.

## What the script does, step by step

| Step | Command | Why |
|---|---|---|
| Enable APIs | `gcloud services enable run artifactregistry cloudbuild secretmanager iam` | A new project has them off. |
| Image repo | `gcloud artifacts repositories create learning-coach` | Somewhere to push Docker images. |
| Service accounts | `lc-app`, `lc-mcp` | Each service runs as its own identity with only the permissions it needs. |
| Secrets | `gcloud secrets versions add NAME --data-file=-` (value piped from `.env`) | Keys go to Secret Manager, not into images or the command line. It only adds a new version when a value has changed. |
| Build | `gcloud builds submit --config deploy/gcp/cloudbuild.yaml` | Builds the 3 Dockerfiles in parallel in the cloud, so local Docker isn't needed. `.gcloudignore` keeps `.env` from being uploaded. |
| MCP servers | `gcloud run deploy ... --no-allow-unauthenticated` + `run.invoker` for `lc-app` | They are private: only the app's service account can call them. |
| App | `gcloud run deploy app --allow-unauthenticated --session-affinity --timeout 3600 --max-instances 1 --set-secrets ...` | Public. Chainlit keeps chats on a websocket and in memory, so it runs one instance with sticky sessions and the 60-minute max timeout. |

The app reaches the private MCP servers by sending a Google-signed ID token. `MCP_AUTH=google` turns this on in
`learning_coach/src/mcp_client/client.py`. Locally `MCP_AUTH` is unset, so nothing changes there.

## Things to know

- **Cost**: everything scales to zero when idle. Cloud Run's free tier covers light use, and you pay only for Artifact Registry storage (cents).
- **Cold start**: the first visit after an idle period takes about 10–20s while the app boots. Add `--min-instances 1` to the app deploy to avoid that, which costs roughly $10–15/month.
- **Memory MCP** keeps its data in process memory, so it is lost when that service scales to zero. It is per-session scratch, so this is fine for now. Moving it to Postgres is the long-term fix.
- **Study notes** are copied into the file-server image when it is built. Edit `learning_coach/study_materials/sample_notes` and redeploy.
- **Supabase free tier** pauses the database after 7 days with no activity. Resume it from the Supabase dashboard.
- **Logs**: `gcloud run services logs read app --region europe-west1 --limit 100`
- **Tear down**: `gcloud run services delete app file-server-mcp memory-server-mcp --region europe-west1`
