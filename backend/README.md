# AI-CAM-RFQ Platform — Backend

## Architecture

```
Frontend (React) → API Gateway (:8000) → Auth Service (:8001)
                                       → CAD Service  (:8002)
                                                ↓ Pub/Sub
                                         CAD Worker (background)
```

## Quick Start

### 1. Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Set up PostgreSQL

Create a database named `mechai`:

```bash
createdb mechai
```

### 3. Initialize tables

```bash
cd backend
python -m scripts.init_db
```

### 4. Run all services (development)

```bash
cd backend
python -m scripts.dev_start
```

This starts:
| Service | Port | Description |
|---------------|-------|--------------------------------|
| API Gateway | 8000 | JWT verification, routing |
| Auth Service | 8001 | Register, Login, JWT issuance |
| CAD Service | 8002 | Model CRUD, signed URLs |
| CAD Worker | — | Background processing (DB poll)|

### 5. Or run services individually

```bash
# API Gateway
uvicorn api_gateway.main:app --port 8000 --reload

# Auth Service
uvicorn auth_service.main:app --port 8001 --reload

# CAD Service
uvicorn cad_service.main:app --port 8002 --reload

# CAD Worker
python -m cad_worker.main
```

## API Routes

All frontend requests go through the API Gateway at `http://localhost:8000/api/v1/`:

### Auth (public)

- `POST /api/v1/auth/register` — Register
- `POST /api/v1/auth/login` — Login
- `GET  /api/v1/auth/me` — Current user (JWT required)

### Models (JWT required)

- `POST /api/v1/models/upload` — Get signed upload URL
- `POST /api/v1/models/confirm-upload` — Confirm upload → triggers processing
- `GET  /api/v1/models/` — List user's models
- `GET  /api/v1/models/{id}` — Get model detail
- `GET  /api/v1/models/{id}/viewer` — Get signed glTF URL (if READY)

## Database Migrations

```bash
# Generate a migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## Project Structure

```
backend/
├── api_gateway/          # Entry point — routes, JWT, logging
│   ├── main.py
│   ├── dependencies.py   # JWT verification
│   ├── middleware.py      # Request logging
│   ├── proxy.py           # httpx async forwarding
│   └── routes/
├── auth_service/         # User auth — register, login, JWT
│   ├── main.py
│   ├── models/           # SQLAlchemy: users table
│   ├── schemas/          # Pydantic request/response
│   ├── services/         # Business logic
│   └── routes/
├── cad_service/          # CAD file management
│   ├── main.py
│   ├── models/           # SQLAlchemy: models table
│   ├── schemas/
│   ├── services/         # Upload, confirm, viewer URL
│   └── routes/
├── cad_worker/           # Background processor (no HTTP)
│   ├── main.py
│   ├── processor.py      # OpenCascade placeholder
│   └── subscriber.py     # Pub/Sub / DB poller
├── shared/               # Cross-service utilities
│   ├── config/           # Settings from env
│   ├── db/               # Async SQLAlchemy session
│   ├── security/         # JWT + password hashing
│   └── schemas/          # Common Pydantic models
├── alembic/              # Database migrations
├── scripts/              # Dev helpers
├── requirements.txt
└── .env
```
