# Mission Control Local Testing & Dogfooding Guide

This guide provides step-by-step instructions for running Mission Control locally on your host machine to verify the full "vertical slice" of Organizations, Projects, Tasks, and the Comms Bridge.

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- [uv](https://github.com/astral-sh/uv) (Python package manager)

---

## Step 1: Core Infrastructure

Start the database and cache:

```bash
./scripts/dev-up.sh
```

---

## Step 2: Server Setup

1. **Install dependencies and run migrations:**
   ```bash
   uv sync
   cd packages/server
   uv run alembic upgrade head
   ```

2. **Initialize local admin account:**
   *(Note: This creates your initial login credentials for local testing)*
   ```bash
   uv run python -m app.scripts.create_local_admin --email johan@example.com --password devpass
   ```

3. **Start the API server:**
   ```bash
   uv run uvicorn app.main:app --reload
   ```
   *The API will be available at http://localhost:8000/docs*

---

## Step 3: Frontend Setup

Open a new terminal:

```bash
cd frontend
npm install
npm run dev
```
*The UI will be available at http://localhost:5173*

---

## Step 4: Initial Configuration (In the Browser)

1. Login to **http://localhost:5173** with the credentials created in Step 2.
2. **Create an Organization:** Give it a name (e.g., "Dogfood Lab").
3. **Create a Project:** Add a project named "Mission Control Development".
4. **Setup an Agent:**
   - Go to **Settings > Users**.
   - Click **Add User** and select **Agent**.
   - Assign the **Admin** role.
   - **IMPORTANT:** Copy the plaintext API Key shown in the one-time display dialog.

---

## Step 5: Comms Bridge Setup

The bridge connects your local Mission Control to the OpenClaw Gateway.

1. **Initialize Bridge Config:**
   ```bash
   cp packages/bridge/comms-bridge.example.yaml packages/bridge/comms-bridge.yaml
   ```

2. **Configure the Bridge:** Edit `packages/bridge/comms-bridge.yaml`:
   - `mc_server_url`: `http://localhost:8000`
   - `mc_api_key`: (Paste the key from Step 4)
   - `mc_org_slug`: (e.g., `dogfood-lab`)
   - `gateway_url`: (Your OpenClaw Gateway URL, e.g., `ws://localhost:9000`)

3. **Install Bridge dependencies:**
   ```bash
   cd packages/bridge
   uv sync
   ```

4. **Start the Bridge:**
   ```bash
   uv run python -m mc_bridge.main --config comms-bridge.yaml
   ```

---

## Step 6: Verify the Loop

1. **Open the MC Chat:** Go to the channel created for your project.
2. **Post a message:** Type something like "Hello from the browser!".
3. **Verify Signal:** Your OpenClaw Gateway should receive the message via the bridge and route it to your active Signal session.
4. **Respond via Signal:** Reply from your phone.
5. **Verify MC:** You should see your Signal response appear in the Mission Control chat in real-time.

---

## Troubleshooting

- **Redis Error:** Ensure Docker is running and `mc-redis` is healthy.
- **Migration Failure:** If the schema is out of sync, try `uv run alembic downgrade -1` or `docker compose -f docker/docker-compose.dev.yml down -v` to wipe the DB.
- **Bridge Connection:** Ensure your OpenClaw Gateway is running and accessible from your host machine.
