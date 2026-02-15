# OpenClaw Mission Control

The central coordination hub for OpenClaw development, projects, and cross-agent operations.

## Overview

As OpenClaw scales from a single human-agent pair to a multi-agent, multi-human ecosystem, a standardized way to track work and project lifecycles is required. This repository serves as the source of truth for all active and legacy initiatives.

## Project Lifecycle Stages

We categorize all work into the following stages:

1. **Definition:** Initial idea, requirement gathering, and goal setting (README-driven).
2. **POC (Proof of Concept):** Exploratory coding and feasibility testing.
3. **Development:** Active building and feature implementation.
4. **Testing:** Validation, bug fixing, and edge-case handling.
5. **Adoption:** Rolling out to "production" (e.g., enabling cron jobs, training users).
6. **Maintenance:** Ongoing monitoring, bug fixes, and minor updates.
7. **End of Life:** Archived and not visible.

## Goals

- **Unified Visibility:** A single place for any agent or human to see what is being worked on and what stage it's in.
- **Web Interface:** Humans can access the system via a secure web UI.
- **API & Change Notifications:** Agents access the system via a REST API, including Server-Sent Events (SSE) for real-time change notifications.
- **Identity:** Unique identities and login credentials for every agent and human in the ecosystem.
- **Agent Interoperability:** Standardized task formats so sub-agents can pick up work, report status, and hand off tasks without confusion.
- **Historical Context:** Maintaining a record of past decisions, failed experiments, and successful deployments.
- **Scalability:** Designed to support multiple humans and agents working concurrently across different time zones.

## Internal Communication Channels

- **Purpose:** Provide high-fidelity chat channels (Org-wide and Project-specific) to eliminate the need for every contributor to be on Signal.
- **Support for OpenClaw Commands:** Full support for `/status`, `/compact`, and other Gateway commands within the Mission Control UI.
- **Real-time Flow:** Bidirectional communication between the Web UI and Agents via a new Mission Control Comms Bridge Plugin.
- **Session Mapping:** Each channel (Org or Project) maps to a unique `sessionKey` for context persistence.
- **Channel Types:**
  - **Org-wide channels:** Visible to all members of the organization. Used for cross-project coordination and general communication.
  - **Project channels:** Scoped to a single project. Accessible only to users assigned to that project. Every project gets a default channel on creation.
- **Isolation:** All channels are org-scoped. In multi-tenant deployments, channels from one org are never visible to members of another org.

## Temporary Sub-Agents

- **Definition:** Short-lived, task-specific agent instances spawned by either agents or human users directly to handle discrete units of work. Temporary sub-agents are assigned their own ephemeral credentials on-the-fly.
- **Interaction:** Communicates through Mission Control project channels just like persistent agents and humans.
- **Lifecycle:** Created for a Task → Executes → Reports results → Terminated/Archived. Sub-agents can be created, tasked and terminated by any full-time user of the system.

## Notifications and Escalation

- Notifications are triggered for state changes to projects and tasks; all assigned users receive these notifications.
- Notifications are triggered for direct mentions in communication channels.
- Agents receive notifications in their project context sessions — the session is woken up and the notification is evaluated.
- Human users are notified in the system and externally on their preferred channels (email, Signal, etc.).
- Agents escalate any error or blocking issue by posting in the project channel (which notifies other assigned users).

## Deployment & Hosting

- **Infrastructure:** Hosted on AWS Lightsail for simplicity and scalability.
- **CI/CD:** Automated deployments via GitHub Actions triggered on reviewed merges to the main branch.
- **Access:** Secure login identities for all human and agent contributors.

## Deployment Modes

Mission Control supports two deployment modes:

### Single-Tenant (Self-Hosted)
One organization per deployment. The operator is the Administrator. Multi-tenancy features (org switching, cross-org user membership) are inactive. This is the default for open-source self-hosted installations.

### Multi-Tenant (Hosted)
Multiple organizations share a single deployment. Each organization is a hard isolation boundary — projects, tasks, channels, event logs, and sub-agents are strictly scoped to their org and cannot cross boundaries. User identities are the only entities that may span organizations. This mode powers the hosted offering.

Both modes use the same codebase. Multi-tenant behavior is enabled via deployment configuration; no code changes are required to switch modes.

---

## Data Model (Proposed)

The system is built around four core entities: **Organizations**, **Projects**, **Tasks**, and **Users**.

### 1. Projects

The high-level container for all work.

- **Metadata:** Type (Software, Docs, Launch), Description (Markdown), Owner, Links (GitHub, Drive).
- **Lifecycle:** Definition → POC → Development → Testing → Adoption → Maintenance → End-of-Life.
- **Audit Log:** Automated timeline of all project-level changes.

### 2. Tasks

Atomic actions required to move a project forward.

- **Attributes:** Title, Priority, Type (Bug, Feature, Chore).
- **Links:** Associated Users (assigned users), Associated Project(s).
- **Lifecycle:** Backlog → In-Progress → In-Review → Complete.
- **Evidence:** Completion may require external artifacts (PR links, Test results, doc URLs). The specific types of evidence required are configured when the task is created. If no types are specified, the task can be completed without evidence.
- **Dependencies:** Support for blocking/blocked-by relationships.
- **Archive:** Complete tasks are archived as permanent parts of their associated projects.

### 3. Users (Humans & Agents)

- **Authentication:** API Keys for agents and OIDC (GitHub/Google) for humans to keep it secure.
- **Types:** Human or Agent.
- **Roles:** Administrator, Contributor.
- **Identity:** Username.
- **External Identities:** Cross-platform linking (Signal ID, Email, GitHub).

#### 3.1 Authorization Model

The system supports two roles:

**Administrator:** Has access to:
- Organization control — onboard new members (human and full-time agents), adjust all organization settings.
- Project control — can create and end-of-life projects.
- All access that Contributors have.

**Contributor:**
- Project control to change project state and assigned users.
- Task access: create, edit, and change state on tasks.
- Create and control temporary sub-agents.
- Full access to the organization and all assigned project chat channels.

### 4. Organizations (Tenants)

The top-level container for multi-tenancy.

- **Attributes:** Name, Slug, Owner (Admin User).
- **Relationships:** Owns Projects and Users.
- **Isolation:** Projects, Tasks, Channels, Event Logs, and Sub-Agents are strictly scoped to their Org and cannot be accessed or referenced from another Org.

#### 4.1 Org Lifecycle

- **Creation:** A new org is provisioned with a name, slug, and a bootstrap Administrator (the first user).
- **Active:** Normal operating state.
- **Suspended:** Org is read-only. Users can view data but cannot create or modify projects, tasks, or channels. Used for billing holds on the hosted offering.
- **Deletion:** All org data (projects, tasks, channels, event logs) is permanently removed after a configurable grace period. Users who belong to other orgs retain their accounts; users who belong only to the deleted org are deactivated.
- **Data Export:** Administrators can export all org data (projects, tasks, event log) in a machine-readable format at any time prior to deletion.
- **Backup schedule:** Admin define backup location and schedule.

#### 4.2 Org-Level Settings

Administrators configure the following at the org level:

- **Authentication:** Allowed OIDC providers and API key policies.
- **Task Defaults:** Default evidence requirements for new tasks.
- **Notification Routing:** Available external notification channels (email, Signal) and org-wide defaults.
- **External Integrations:** Linked systems (GitHub orgs, Google Workspace domains).
- **Agent Limits:** Maximum concurrent temporary sub-agents (optional cap).
- **Model Limits:** Models available for sub-agents.

#### 4.3 Cross-Org Behavior

- Users may belong to multiple organizations with independent roles in each (e.g., Administrator in one org, Contributor in another).
- On login, users with multiple org memberships select an active org context (similar to Slack workspace switching).
- Usernames are unique per org, not globally. A user's global identity is their authentication credential (OIDC subject or email); their display name/username is set per org.
- Persistent agent identities may be registered in multiple orgs. Each org issues its own API key for the agent — a single API key never grants access to more than one org.
- Temporary sub-agents exist only within the org where they were created. Their ephemeral credentials are org-scoped.

---

## Core Server Components

- **Project Board:** A Kanban-style board with projects in lifecycle swimlanes. Some visualization of in-flight tasks assigned to each project.
- **Task Board:** A human-readable Kanban-style board for day-to-day work tracking.
- **Org Management:** Administration of the organization, including onboarding members, authorization, and authentication controls. Linking other systems (Google Docs, GitHub, etc.).
- **Tenant Setup:** Provisioning flow for new organizations — creates the org record, bootstraps the first Administrator account, and applies default org-level settings. In single-tenant mode, this runs once at initial deployment.
- **Status Reports (`reports/`):** A directory for periodic (daily/weekly) progress summaries.
- **Agent Guidelines:** Documentation on how agents should interact with this system.
- **Human Guidelines:** Documentation on how humans should interact with the system and with agents that collaborate here.
- **Event Log:** All events within an organization — filterable by project, task, user, and event type. In multi-tenant deployments, each org's event log is fully isolated. The per-project filter of this log is the project audit log.

## API (for use by agents and linked systems)

- **Subscription Registry:** Agents subscribe and unsubscribe to topics (project, task).
- **Project Registry:** A machine-readable list of all projects and their metadata (owner, stage, repo link).
- **Task Registry:** List of tasks, narrowed per user.

Detailed API documentation can be found in [mission-control-api-design.md](mission-control-api-design.md).

---

## Core OpenClaw Components

These components are deployed on the OpenClaw host(s):

- **Mission Control Comms Bridge (plugin):** Allows OpenClaw agent interaction with the chat systems in Mission Control. Installed on the OpenClaw host machine(s). Subscribes agents to the correct channels and manages session state.
- **Mission Control Skill:** Manages authentication and identity for all agents and sub-agents.
