# Mission Control Local Testing & Dogfooding Guide

This guide provides step-by-step instructions for running Mission Control locally on your host machine to verify the full "vertical slice" of Organizations, Projects, Tasks, and the Comms Bridge.

## Prerequisites

- Python 3.12+
- Node.js 20+
- Homebrew (for Mac native setup)
- [uv](https://github.com/astral-sh/uv) (Python package manager)

---

## Step 1: Infrastructure Setup

You have two choices for running PostgreSQL and Redis. Native is recommended for development on Mac to avoid virtualization overhead.

### Option A: Native Setup (Recommended for Mac)

1.  **Install the services:**
    ```bash
    brew install postgresql@16 redis
    ```

2.  **Start the services:**
    ```bash
    brew services start postgresql@16
    brew services start redis
    ```

3.  **Create the 'postgres' superuser:**
    *Note: Homebrew Postgres creates a user matching your system name, but the app expects 'postgres'.*
    ```bash
    createuser -s postgres
    psql -d postgres -c "ALTER USER postgres WITH PASSWORD 'postgres';"
    ```

4.  **Create the database:**
    ```bash
    createdb mission_control
    ```

### Option B: Docker Setup

*Note: If running inside a VM, ensure "Nested Virtualization" is enabled in your hypervisor settings.*

```bash
./scripts/dev-up.sh
```

---

## Step 2: Server Setup

1.  **Install dependencies and link workspace:**
    *Run this from the project root:*
    ```bash
    uv sync
    ```

2.  **Run migrations:**
    ```bash
    cd packages/server
    uv run alembic upgrade head
    ```

3.  **Initialize local admin account:**
    ```bash
    uv run python -m app.scripts.create_local_admin --email your@email.com --password yourpassword
    ```

4.  **Start the API server:**
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
2. **Select the Default Organization:** The setup script automatically creates a "Default Organization" for you.
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
   - `mc_org_slug`: `default`
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

### Database Issues
- **"role 'postgres' does not exist":** See Step 1 (Option A, #3) to create the role.
- **"column does not exist":** Your schema is out of sync. Run the reset utility:
  ```bash
  ./scripts/db-reset.sh
  ```
- **Timezone errors:** Ensure all model fields use `sa_type=sa.DateTime(timezone=True)`.

### Python Environment
- **ModuleNotFoundError:** Ensure you ran `uv sync` from the **root** of the repository to link workspace packages.
- **Bcrypt/Passlib errors:** If you see `AttributeError: module 'bcrypt' has no attribute '__about__'`, ensure you have pinned `bcrypt==4.0.1`.

### Network & Security
- **403 Forbidden on API:** Likely an expired JWT or a CSRF issue. Try logging out and back in.
- **CSP Errors in /docs:** Ensure `app/core/middleware.py` allows `https://cdn.jsdelivr.net`.
