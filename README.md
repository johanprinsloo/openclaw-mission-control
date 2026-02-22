# Mission Control

**Problem Statement**
Most humans have a good idea of how AI agents can help them with projects or tasks. They do not, however, typically have the technical know-how to set up, prompt, and manage agents.
The goal for this project is to make agent collaboration natural. The context of Organization -> Projects -> Tasks provides agents with the necessary background to complete assigned tasks effectively.
The same is true for the collaborating humans: the project gives them a simple way to manage a team of humans and agents toward well-defined goals.

The project will also strive to make it easier to create and manage temporary and full-time agents without the usual techno wizardry required.

**Coordination hub for OpenClaw agents and human teams.**

Mission Control is a project management system designed for human-agent collaboration. It provides a shared workspace where humans and AI agents can manage projects, track tasks, communicate in real-time, and coordinate work.

## Status

🚧 **Under Active Development** — Currently in the Foundation stage.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Mission Control                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  Frontend   │    │   Server    │    │   Bridge    │         │
│  │  (Vue 3)    │◄──►│  (FastAPI)  │◄──►│  (Python)   │         │
│  └─────────────┘    └──────┬──────┘    └──────┬──────┘         │
│                            │                   │                │
│                     ┌──────┴──────┐     ┌──────┴──────┐        │
│                     │ PostgreSQL  │     │  OpenClaw   │        │
│                     │   + Redis   │     │   Gateway   │        │
│                     └─────────────┘     └─────────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Repository Structure

```
openclaw-mission-control/
├── packages/
│   ├── server/         # FastAPI backend (API, auth, real-time)
│   ├── shared/         # Shared Pydantic schemas
│   └── bridge/         # OpenClaw ↔ MC communications bridge
├── frontend/           # Vue 3 + TypeScript + Tailwind
├── docker/             # Docker Compose configurations
├── scripts/            # Development and deployment scripts
├── docs/               # Design documents and specs
└── poc/                # Proof-of-concept implementations
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker and Docker Compose
- [uv](https://github.com/astral-sh/uv) (Python package manager)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/johanprinsloo/openclaw-mission-control.git
   cd openclaw-mission-control
   ```

2. **Copy environment configuration**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start PostgreSQL and Redis**
   ```bash
   ./scripts/dev-up.sh
   ```

4. **Install Python dependencies and run migrations**
   ```bash
   uv sync
   cd packages/server
   uv run alembic upgrade head
   ```

5. **Start the API server**
   ```bash
   cd packages/server
   uv run uvicorn app.main:app --reload
   ```

6. **Start the frontend** (in a new terminal)
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

7. **Access the application**
   - Frontend: http://localhost:5173
   - API Docs: http://localhost:8000/docs

## Documentation

Design documents and specifications are in the `docs/` directory:

- [API Design](docs/mission-control-api-design.md)
- [Persistence Strategy](docs/mission-control-persistence-strategy.md)
- [Tech Stack](docs/mission-control-tech-stack.md)
- [Security Stance](docs/mission-control-security-stance.md)
- [Frontend Architecture](docs/mission-control-frontend-architecture.md)
- [Comms Bridge Spec](docs/mission-control-comms-bridge-spec.md)
- [Implementation Plan](docs/mission-control-implementation-plan.md)
