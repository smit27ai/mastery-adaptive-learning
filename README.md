# Mastery — An Adaptive Learning Engine

Instead of predicting a label, this system predicts a learner's **evolving knowledge
state** and then decides what to teach next.

A learner's mastery of a concept is latent and time-varying: it has to be inferred from
noisy interaction data, and the best next question depends on that hidden state. That
single idea is what makes classical ML, deep learning, NLP and reinforcement learning
structurally necessary here rather than decorative.

Full project brief: [`Mastery_Adaptive_Learning_Engine.md`](Mastery_Adaptive_Learning_Engine.md)

---

## Quick start

No Postgres, no Redis, no Docker needed for the first run — the app defaults to SQLite
with an in-process cache.

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev,dashboard]"    # Linux/macOS: .venv/bin/pip
cp .env.example .env
.venv/Scripts/python -m mastery.data.seed
.venv/Scripts/uvicorn mastery.api.main:app --reload
```

Then open:

| URL | What |
|---|---|
| http://localhost:8000/docs | Swagger UI — click through the whole API |
| http://localhost:8000/health | Liveness |
| http://localhost:8000/ready | Readiness (database, cache, models) |
| http://localhost:8000/metrics | Prometheus metrics |

Demo accounts created by the seed: `student@demo.local` / `instructor@demo.local`,
password `demo12345` (override with `DEMO_PASSWORD`). In production the seed refuses
to create these accounts while that password is still the default, so a public
deployment never ships with credentials that are printed in this file.

Student app (Next.js), in a second terminal:

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000 - it signs in as the demo student automatically, serves an
adaptively chosen question, and animates the mastery bars as you answer. This is the
five-minute demo: answer questions and watch the bars move and the difficulty follow.

Instructor dashboard, in a third terminal:

```bash
streamlit run src/mastery/dashboard/app.py
```

Full stack against real Postgres and Redis:

```bash
docker compose up --build
```

---

## What runs today

The thin end-to-end slice is live and tested: a learner authenticates, receives an
adaptively chosen question, answers it, and their per-concept mastery moves.

| Layer | Status |
|---|---|
| FastAPI service, JWT auth, role gating, rate limiting | working |
| Bayesian Knowledge Tracing (inference + Baum-Welch fitting) | working |
| IRT 2PL difficulty targeting | working |
| Thompson-sampling contextual bandit tutor | working |
| Real-time anomaly rules (guessing, disengagement) | working |
| Prediction logging for drift detection and retraining | working |
| Prometheus metrics, structured logs, health/readiness | working |
| Next.js student app with animated mastery bars | working |
| Streamlit instructor dashboard | working |
| Docker, docker-compose, GitHub Actions CI | working |
| Deep knowledge tracing (LSTM/SAKT via ONNX) | slot reserved in the fallback chain |
| XGBoost risk model + SHAP | endpoint contract in place, heuristic behind it |
| NLP doubt routing, embeddings answer grading | not started |
| Learner clustering, fairness audit | not started |
| MLflow registry, Evidently drift, retraining pipeline | not started |

Everything not yet built has its seam already cut, so adding it does not require
rewriting what works.

---

## Architecture

```
Next.js student app ──┐
Streamlit dashboard ──┴─► FastAPI ──┬─► Postgres   (users, attempts, snapshots, predictions)
                                     ├─► Redis      (mastery cache, sessions, rate limits)
                                     └─► S3 / R2    (model artifacts, datasets)

                      Offline: MLflow registry + nightly retrain + Evidently drift
```

### The two endpoints that matter

**`GET /next-question`** — load mastery (cache, else replay BKT over the attempt log),
build features for a candidate pool, score each with the model chain, let the bandit
choose, log the prediction with its features.

**`POST /submit-answer`** — persist the attempt, Bayesian-update mastery, snapshot it,
check anomaly rules, close the loop on the logged prediction, invalidate the cache.

### Four decisions worth defending in a viva

**One feature module, imported by both training and serving.**
`src/mastery/features/builder.py` is the only place features are computed, and it
asserts that its output matches `FEATURE_NAMES`. Features computed one way in a notebook
and another way in the API is *train/serve skew* — the model degrades silently and
nothing errors. This is the most common way a deployed ML project dies.

**Models load once, at startup.** `ModelRegistry.load()` runs in the FastAPI lifespan.
Loading per request turns a 50ms endpoint into a 3s one.

**Inference degrades, it never fails.** `DKT (ONNX) → BKT → item p-value → uniform`.
BKT is pure arithmetic with no artifact to load, so the chain cannot fully fail. During
a live demo a 500 is unrecoverable; a slightly worse question is not.

**Deep models are served through ONNX, not PyTorch.** Train on a free Colab/Kaggle GPU,
export the `.onnx`, and ship a ~250MB image instead of ~2.5GB. On free-tier hosting that
is the difference between the app starting and not.

### Two decisions in the student app

**Animations never gate content.** Nothing the learner has to read fades in from
`opacity: 0`, and no layout animates `height: "auto"`. Both patterns leave text invisible
if the animation stalls or never runs - a throttled tab, a device dropping
`requestAnimationFrame`, reduced-motion. Entrances animate transform only, so the worst
case is text a few pixels off rather than text that is not there. The mastery bars
animate width from their previous value, which encodes the change itself.

**Disabled options do not respond to hover.** CSS `:hover` still matches a disabled
button, so a plain `hover:border-accent` rule paints whatever option the cursor rests on
with the same border that means "your selection". Mid-demo that reads as a second answer
being chosen. The rule is scoped with `enabled:`.

---

## Layout

```
web/            Next.js 15 student app (React 19, Tailwind, motion)
  app/          routes and global styles
  components/   MasteryBars, QuestionCard
  lib/api.ts    typed client mirroring the Pydantic schemas
src/mastery/
  api/          FastAPI app, routers, dependencies
  common/       config, structured logging, schemas, security
  data/         dataset loaders and the demo seed
  db/           ORM models, async session, cache
  dashboard/    Streamlit instructor view
  features/     THE shared feature module
  models/       bkt, irt, bandit, anomaly, registry
  services/     the learning loop, testable without HTTP
tests/          unit + end-to-end API tests
migrations/     Alembic
Dockerfile      production image, at the root so hosts auto-detect it
docker/         entrypoint script
```

---

## Development

```bash
make test        # pytest with coverage
make lint        # ruff
make typecheck   # mypy
make check       # everything CI runs
make fmt         # black + ruff --fix
```

Migrations:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

Never hand-edit a production schema — the migration is the record of what changed.

---

## Configuration

Every setting comes from the environment (see `.env.example`). Nothing environment-
specific is committed, and `.env` is gitignored.

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | SQLite file | `postgresql+asyncpg://…` in production |
| `REDIS_URL` | empty | Empty means in-process cache; the app still works |
| `JWT_SECRET` | dev placeholder | **Must** be a long random string in production |
| `TARGET_SUCCESS_RATE` | `0.7` | The difficulty the tutor aims the learner at |
| `EXPLORATION_RATE` | `0.15` | Exploration weight in the bandit |
| `MODEL_DIR` | `./models/artifacts` | Where `dkt.onnx` is looked up |
| `AUTO_CREATE_SCHEMA` | `true` | `false` in production - Alembic owns the schema |
| `DEMO_PASSWORD` | `demo12345` | Must be changed for the seed to run in production |
| `SEED_DEMO_DATA` | `false` | Set `true` once to load the demo curriculum on deploy |
| `CORS_ORIGIN_REGEX` | empty | Allows Vercel preview hostnames without widening to `*` |
| `CORS_ORIGINS` | localhost | Comma-separated allowlist |

---

## Deployment

The API ships as a container; the student app is a static Next.js build.

| Piece | Host | Notes |
|---|---|---|
| API | Railway | Auto-detects the root `Dockerfile`, health check on `/health` |
| Postgres | Railway plugin | `DATABASE_URL` is injected |
| Redis | Railway plugin (optional) | Omit it and the app uses its in-process cache |
| Student app | Vercel | Root directory `web`, `NEXT_PUBLIC_API_URL` points at the API |

Migrations run in the container entrypoint, not the application lifespan: schema changes
must happen once per deploy before any worker serves traffic, rather than racing across
replicas. The entrypoint also binds `$PORT`, which Railway injects.

`DATABASE_URL` can be wired straight from the provider. Managed Postgres hands out
`postgres://` or `postgresql://`, and the settings layer rewrites either onto
`postgresql+asyncpg://` — otherwise the async engine fails at startup with an opaque
dialect error, in production, on the first deploy.

Required Railway variables:

```
APP_ENV=production
AUTO_CREATE_SCHEMA=false
JWT_SECRET=<64 random characters>
DEMO_PASSWORD=<your own>
SEED_DEMO_DATA=true          # first deploy only
CORS_ORIGINS=https://<your-app>.vercel.app
CORS_ORIGIN_REGEX=^https://<your-project>-[a-z0-9-]+\.vercel\.app$
```

Required Vercel variable:

```
NEXT_PUBLIC_API_URL=https://<your-api>.up.railway.app
```

The two reference each other, so deploy the API first, then the web app with the API's
URL, then set `CORS_ORIGINS` to the web app's URL and redeploy the API.

---

## Datasets

Public interaction logs, no scraping required:

- **ASSISTments 2009/2017** — small and clean; start here, iterate in seconds
- **RIIID Answer Correctness** (Kaggle) — ~100M rows; use Polars or chunked Parquet,
  pandas will run out of memory
- **EdNet KT1** — largest, add last

Split by **time and by learner**, never at random. A random split leaks the future into
the training set and inflates every metric you report.

---

## Roadmap

| Phase | Work |
|---|---|
| 1 | Ingest ASSISTments, EDA, feature pipeline, time-ordered splits |
| 2 | LogReg / DT / SVM / NB → RF / XGBoost / stacking, tuned with Optuna, logged to MLflow |
| 3 | BKT vs IRT vs DKT vs SAKT on one split — the accuracy/interpretability trade-off is the thesis |
| 4 | Clustering, NLP doubt routing, embedding-based answer grading, Isolation Forest |
| 5 | Simulated learner, then ε-greedy / UCB / Thompson / Q-learning compared against random and fixed order |
| 6 | SHAP on the risk model, fairness audit across cohorts |
| 7 | Load testing, backups, restore drill, alerting |
| 8 | MLflow promotion gates, Evidently drift, nightly retraining |
| 9 | Polish the student app, rehearse the 5-minute demo |
