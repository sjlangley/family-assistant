# Docker Compose Setup

This guide explains how to run the Family Assistant application stack using Docker Compose.

## Overview

The Docker Compose setup includes:

- **PostgreSQL** - Database for storing user data, conversations, and memories
- **Backend** - FastAPI application serving the API (`assistant-backend`)
- **Frontend** - React application serving the UI (`assistant-ui`)

**Note:** The LLM server runs separately on your host machine. See `apps/llm-server/README.md` for setup instructions.

## Prerequisites

- **Docker** and **Docker Compose** installed
- **LLM Server** running on your host machine (see `apps/llm-server/README.md`)
- **Google OAuth credentials** (see setup instructions below)

## Quick Start

### 1. Configure Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your configuration
# Minimum required changes:
# - GOOGLE_OAUTH_CLIENT_ID (both variables)
# - VITE_GOOGLE_CLIENT_ID
# - SESSION_SECRET_KEY
# - POSTGRES_PASSWORD
```

### 2. Generate Session Secret Key

```bash
# Generate a secure random session secret
openssl rand -hex 32
# Copy the output to SESSION_SECRET_KEY in .env
```

### 3. Set Up Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new OAuth 2.0 Client ID (or use existing)
3. Add authorized JavaScript origins:
   - `http://localhost:3000`
   - `http://localhost:5173` (for Vite dev server)
4. Add authorized redirect URIs:
   - `http://localhost:3000`
5. Copy the Client ID to both `GOOGLE_OAUTH_CLIENT_ID` and `VITE_GOOGLE_CLIENT_ID` in `.env`

### 4. Start the LLM Server

The backend needs an LLM server to be running. Follow the instructions in `apps/llm-server/README.md` to:

```bash
# Example: Start llama.cpp server (adjust based on your setup)
# See apps/llm-server/README.md for detailed instructions
./llama-server \
  --model path/to/model.gguf \
  --port 8000 \
  --chat-template llama3
```

### 5. Build and Start Services

```bash
# Build and start all services
docker compose up --build

# Or run in detached mode
docker compose up --build -d
```

The services will be available at:

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8080
- **Backend Health**: http://localhost:8080/health
- **PostgreSQL**: localhost:5432

### 6. View Logs

```bash
# View logs from all services
docker compose logs -f

# View logs from a specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres
```

## Service Management

### Stop Services

```bash
# Stop services (preserves data)
docker compose stop

# Stop and remove containers (preserves data volumes)
docker compose down
```

### Restart Services

```bash
# Restart all services
docker compose restart

# Restart a specific service
docker compose restart backend
```

### Rebuild After Code Changes

```bash
# Rebuild and restart specific service
docker compose up --build backend

# Rebuild all services
docker compose up --build
```

## Data Management

### Database Persistence

PostgreSQL data is stored in a Docker volume named `family-assistant_postgres_data`. Data persists across container restarts.

### Reset Database

```bash
# WARNING: This deletes all database data
docker compose down -v

# Start fresh
docker compose up --build
```

### Backup Database

```bash
# Create a backup
docker compose exec postgres pg_dump -U assistant family_assistant > backup.sql

# Restore from backup
cat backup.sql | docker compose exec -T postgres psql -U assistant family_assistant
```

## Development Workflow

### Running Tests

```bash
# Run backend tests
cd apps/assistant-backend
python3 -m pytest

# Run frontend tests
cd apps/assistant-ui
npm test
```

### Local Development (without Docker)

For faster development iteration, you can run services locally:

```bash
# Terminal 1: Start LLM server
# See apps/llm-server/README.md

# Terminal 2: Start backend
cd apps/assistant-backend
source .venv/bin/activate  # or create venv
pip install -e ".[dev]"
uvicorn assistant.app:app --reload --port 8080

# Terminal 3: Start frontend
cd apps/assistant-ui
npm install
npm run dev  # Runs on port 5173
```

## Troubleshooting

### Frontend can't connect to backend

- Check that `VITE_API_BASE_URL` in `.env` matches your backend URL
- For Dockerized setup: `http://localhost:8080`
- For local dev: `http://localhost:8080` or `http://localhost:5173` depending on your setup

### Backend can't connect to LLM server

- Ensure LLM server is running on your host machine
- Check `LLM_BASE_URL` uses `host.docker.internal` for Docker setup
- Verify the port matches your LLM server port (default: 8000)
- Test: `curl http://localhost:8000/v1/models`

### Google OAuth errors

- Verify both OAuth client IDs are identical in `.env`
- Check authorized origins include your frontend URL
- Ensure the OAuth consent screen is configured

### Database connection errors

- Check `POSTGRES_PASSWORD` is set in `.env`
- Ensure PostgreSQL service is healthy: `docker compose ps`
- View logs: `docker compose logs postgres`

### Port conflicts

If ports are already in use, override them in `.env`:
```bash
FRONTEND_PORT=3001
BACKEND_PORT=8081
POSTGRES_PORT=5433
```

## Architecture Notes

### Networking

Services communicate via a private Docker network (`family-assistant-network`). The backend connects to:

- PostgreSQL at `postgres:5432` (internal network)
- LLM server at `host.docker.internal:8000` (host machine)

### Health Checks

All services have health checks configured:

- **PostgreSQL**: Checks database readiness
- **Backend**: Checks `/health` endpoint
- **Frontend**: Checks HTTP server response

Services wait for their dependencies to be healthy before starting.

### Build Process

- **Backend**: Multi-stage Docker build with Python 3.14
- **Frontend**: Multi-stage build (Node build → serve static files)
- Build args inject environment variables into the frontend bundle

## Production Considerations

For production deployments:

1. **Use strong passwords**: Change `POSTGRES_PASSWORD` and `SESSION_SECRET_KEY`
2. **Enable HTTPS**: Set `ENVIRONMENT=production` and configure reverse proxy
3. **Secure secrets**: Use Docker secrets or environment variable injection
4. **Resource limits**: Add resource constraints to docker-compose.yml
5. **Monitoring**: Configure logging aggregation and health monitoring
6. **Backup strategy**: Implement automated database backups
7. **Update origins**: Set proper `CLIENT_ORIGINS` for your domain

## Additional Resources

- [Backend README](apps/assistant-backend/README.md)
- [Frontend README](apps/assistant-ui/README.md)
- [LLM Server Setup](apps/llm-server/README.md)
- [Architecture Documentation](docs/ARCHITECTURE.md)
