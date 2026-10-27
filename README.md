# DroneCrop AI

DroneCrop AI is a responsive crop-imaging dashboard with a React/Vite frontend and a FastAPI backend. The backend accepts JPG/PNG uploads, performs inference only when a local classifier is configured, and persists successful results and image files to SQLite and local storage. Missing hardware and model integrations are reported as unavailable; the app does not simulate a live drone or produce placeholder predictions.

## Current integration status

| Integration | Status |
| --- | --- |
| Dashboard, monitoring, analysis, map, history, recommendations, settings | Implemented |
| Image upload and server-side validation | Implemented; inference requires `MODEL_PATH` to point to a compatible local model |
| Detection history, filters, pagination, CSV export, stats | Implemented with SQLite |
| GPS association | Optional coordinates can be submitted with an image; no GPS receiver is connected |
| ESP32-CAM | Not connected; camera capture and monitoring controls remain unavailable |
| APM 2.8 telemetry | Not connected; no flight-control or motor-arming commands exist |
| Plant disease classifier | Bundled under `backend/models/plantvillage-mobilenetv2`; configure `MODEL_PATH` to enable inference |
| Vercel / Render | Configuration and deployment guidance included; not deployed from this workspace |

## Architecture

- `src/`: React pages, reusable shell, API client, charts, Leaflet/OpenStreetMap map.
- `backend/app/`: FastAPI endpoints, local image-classifier adapter, SQLite storage and response schemas.
- `backend/tests/`: API tests.
- The UI gets all counts, detection rows, connection statuses and map points from backend endpoints. No demo data mode is enabled.
- Images are kept as generated-name files under `UPLOADS_PATH`; database rows contain a relative image endpoint, not base64.

## Prerequisites

- Node.js 20.19+ or 22.12+ and npm (Vite 8 requirement).
- Python 3.10+ (Python 3.11 or 3.12 is recommended for compatibility with optional PyTorch model dependencies).

## Local development

### Backend

From the repository root in PowerShell:

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

If you use another Python version, replace `py -3.12` with the installed interpreter. The `.env` file is optional; the defaults run the API locally and keep its SQLite database and images in `backend\data\` and `backend\uploads\`.

### Frontend

In a second PowerShell terminal:

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open the local Vite URL printed by npm. The frontend defaults to `http://localhost:8000` for the API. Set `VITE_API_BASE_URL` in `.env.local` before starting Vite to use a different backend. Vite environment variables are build-time values; changing them requires restarting the dev server or rebuilding.

## Environment variables

Backend variables are documented in [`backend/.env.example`](./backend/.env.example):

| Variable | Purpose |
| --- | --- |
| `DATABASE_PATH` | SQLite file path; default `backend/data/detections.sqlite3` from repository root |
| `UPLOADS_PATH` | Image storage directory; default `backend/uploads` |
| `CORS_ORIGINS` | Comma-separated exact allowed browser origins |
| `MAX_UPLOAD_BYTES` | Maximum image size; defaults to 10 MiB |
| `GPS_MAX_SKEW_SECONDS` | Maximum time difference allowed between a valid GPS fix and image capture; default 30 seconds |
| `MODEL_PATH` | Local model folder; unset means inference is unavailable |
| `MODEL_NAME`, `MODEL_VERSION` | Model metadata returned with predictions |
| `MODEL_SCORE_THRESHOLD` | Below this raw model score, classification is inconclusive; default `0.55` |
| `ENVIRONMENT` | Set to `production` to reject wildcard CORS |

Frontend variables are documented in [`.env.example`](./.env.example):

| Variable | Purpose |
| --- | --- |
| `VITE_API_BASE_URL` | Base URL used by the centralized frontend API client |

Never place server-side credentials or private keys in frontend variables.

## Bundled model and limitations

The repository includes a MobileNetV2 classifier at `backend/models/plantvillage-mobilenetv2`, with its configuration, preprocessing settings and weights. Set `MODEL_PATH` to this directory to load it at backend startup; for a Render service whose root directory is `backend`, use `models/plantvillage-mobilenetv2`. The checkpoint is stored directly in Git so deployment checkouts receive the model weights rather than an unresolved Git LFS pointer. Runtime dependencies are listed in `backend/requirements.txt`.

The bundled model provides 38 PlantVillage classes for 14 crops. **Rice is not among its labels.** The model card reports high accuracy on held-out PlantVillage images, but field imagery differs; outputs are screening suggestions only. Classifier scores returned by this API are raw softmax model scores and should not be described as calibrated confidence.

An unrelated external model candidate was also reviewed at [Hugging Face: `linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification`](https://huggingface.co/linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification). Its model card identifies a PyTorch/Transformers MobileNetV2 image classifier, fine-tuned on the PlantVillage dataset, with a 224-pixel image input and a 9,335,093-byte `pytorch_model.bin`. Its published config contains these 38 labels:

- Apple: `Apple Scab`, `Apple with Black Rot`, `Cedar Apple Rust`, `Healthy Apple`
- Blueberry: `Healthy Blueberry Plant`
- Cherry: `Cherry with Powdery Mildew`, `Healthy Cherry Plant`
- Corn (Maize): `Corn (Maize) with Cercospora and Gray Leaf Spot`, `Corn (Maize) with Common Rust`, `Corn (Maize) with Northern Leaf Blight`, `Healthy Corn (Maize) Plant`
- Grape: `Grape with Black Rot`, `Grape with Esca (Black Measles)`, `Grape with Isariopsis Leaf Spot`, `Healthy Grape Plant`
- Orange: `Orange with Citrus Greening`
- Peach: `Peach with Bacterial Spot`, `Healthy Peach Plant`
- Bell Pepper: `Bell Pepper with Bacterial Spot`, `Healthy Bell Pepper Plant`
- Potato: `Potato with Early Blight`, `Potato with Late Blight`, `Healthy Potato Plant`
- Raspberry: `Healthy Raspberry Plant`
- Soybean: `Healthy Soybean Plant`
- Squash: `Squash with Powdery Mildew`
- Strawberry: `Strawberry with Leaf Scorch`, `Healthy Strawberry Plant`
- Tomato: `Tomato with Bacterial Spot`, `Tomato with Early Blight`, `Tomato with Late Blight`, `Tomato with Leaf Mold`, `Tomato with Septoria Leaf Spot`, `Tomato with Spider Mites or Two-spotted Spider Mite`, `Tomato with Target Spot`, `Tomato Yellow Leaf Curl Virus`, `Tomato Mosaic Virus`, `Healthy Tomato Plant`

**Rice is not among its labels.**

The external candidate's published card reports 95.41% evaluation accuracy; this is the card's reported metric, not a calibrated probability or a guarantee on drone imagery.

The external candidate's Hugging Face metadata states `license: other` and does not provide clear usage terms in the model card. **Those external weights are not downloaded or enabled by this project.** Verify applicable model and dataset usage rights before adopting other models.

To use a different compatible classifier, install compatible CPU or GPU versions of `torch` and `transformers`, then set `MODEL_PATH` to a local folder containing at least:

- `config.json` with the classifier architecture and `id2label` mapping
- `preprocessor_config.json` with the model's actual image preprocessing settings
- `pytorch_model.bin` or `model.safetensors` with the trained weights

The adapter loads a model once at process startup, uses its processor and labels, returns up to three raw-score predictions, and marks results below the configured threshold inconclusive. Do not point it at an unreviewed or unlicensed model. The deployment platform must have enough memory and disk for the model and its inference framework.

## API

| Method | Endpoint | Behavior |
| --- | --- | --- |
| `GET` | `/health` | Backend and model availability |
| `GET` | `/api/status` | Camera, GPS, model and telemetry status |
| `POST` | `/api/predict` | Validate image, run configured model and persist result; optional GPS values require paired coordinates, a valid-fix flag and timezone-aware timestamps |
| `GET` | `/api/detections` | Search/filter/page saved detection records |
| `GET` | `/api/detections/{detection_id}` | One saved record |
| `GET` | `/api/locations` | Paginated records with valid coordinates |
| `GET` | `/api/stats` | Counts, crop-wise disease distribution and 14-day activity calculated from stored records |
| `GET` | `/api/images/{filename}` | Serve an image stored by the API |

`/api/predict` returns HTTP 503 when no model is loaded; it never substitutes a fake result. Uploads are limited to JPG/PNG and 10 MiB by default. GPS coordinates are stored only when both values are supplied with an asserted valid fix and timezone-aware GPS/capture timestamps within `GPS_MAX_SKEW_SECONDS` of one another. This validates submitted metadata, not the physical GPS hardware; only send coordinates that the calling system has reliably associated with the capture.

## Tests and production build

From the repository root:

```powershell
python -m pytest backend\tests
npm run lint
npm run build
```

Tests cover backend/model-unavailable behavior, status reporting, validation and empty history/stats. They do not validate pretrained inference because no licensed model is installed.

## Deployment

### Vercel frontend

- Import the repository and use the default Vite build command, `npm run build`, with output directory `dist`.
- [`vercel.json`](./vercel.json) rewrites frontend routes to `index.html` for React Router.
- Set `VITE_API_BASE_URL` to the public HTTPS Render API URL in the Vercel project environment, then redeploy.
- Add the exact Vercel production/preview origins to the backend `CORS_ORIGINS`.

### Render backend

- Create a Python web service with root directory `backend`.
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Configure `CORS_ORIGINS` with only the frontend origins; set `ENVIRONMENT=production`.
- `/health` is the service health-check path.
- Render's ordinary local filesystem is ephemeral. Attach a persistent disk and set `DATABASE_PATH` and `UPLOADS_PATH` under its mount path, or migrate to managed PostgreSQL and object storage before production/scaling. A single SQLite file and local upload directory are not a multi-instance storage design.
- If installing a model, provision sufficient disk/RAM and install framework versions compatible with the selected model and Render's Python runtime. Model loading increases startup time and memory.

## Hardware integration safety

The ESP32-CAM, GPS receiver and APM 2.8 are intentionally treated as separate future integrations. A safe next step is a backend-mediated image upload endpoint and timestamped GPS metadata, followed by a read-only telemetry service using a supported serial/network bridge. Validate fix quality and capture-time alignment before attaching a location. Do not expose device credentials to the browser, forward arbitrary commands, or add arming/flight-control behavior to this web UI.
