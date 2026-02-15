# Mission Control: Deferred Features (v2+)

This document tracks features and architectural enhancements that have been identified as valuable but are outside the scope of the v1 MVP. These items are deferred to focus on core stability, agent-human collaboration, and multi-tenant isolation.

## Architectural Enhancements

### 1. Dedicated Search Engine
- **V1:** PostgreSQL Full-Text Search (FTS) with GIN indexes and `ts_rank`.
- **V2:** Pluggable search backends (e.g., Typesense, Meilisearch) for improved latency, typo tolerance, and complex faceted filtering in high-volume hosted environments.

### 2. Automated Cold Storage Implementation
- **V1:** Documented "Cold Tier" concept; partitions detached manually or via simple scripts.
- **V2:** Automated lifecycle management (pg_partman or similar) that detach, compress, and upload old message/event partitions to S3 with a searchable metadata index.

### 3. Granular Field-Level Permissions
- **V1:** Role-based access (Admin, Contributor) with org-level isolation.
- **V2:** Attribute-based access control (ABAC) allowing for field-level restrictions (e.g., only project owners can change project descriptions) or private tasks within a shared project.

### 4. Multi-Region Data Residency
- **V1:** Single-region deployment (AWS US-West-2).
- **V2:** Logic to route tenants to specific regional database instances (e.g., EU-Central-1) to satisfy GDPR or other regulatory data residency requirements.

## Functional Features

### 5. Advanced Interactive Visualizations
- **V1:** Kanban boards (Projects, Tasks) and simple list views.
- **V2:** Interactive GANTT charts, project timelines, and workload heatmaps for resource planning.

### 6. Two-Way External System Sync
- **V1:** Static links to GitHub/Docs and evidence URLs.
- **V2:** Deep integration with external issue trackers (GitHub Issues, Jira, Linear) allowing status and comment synchronization.

### 7. Custom Task Types and Schemas
- **V1:** Fixed task types (bug, feature, chore) and standard fields.
- **V2:** Custom task types per org with user-defined fields (e.g., "Due Date", "Estimation Points", "Customer ID").

### 8. Automated Dependency Management
- **V1:** Manual blocking/blocked-by relationships.
- **V2:** Automated conflict detection, critical path analysis, and "agent-assisted" rescheduling when a blocker is updated.

### 9. Advanced Analytics Dashboard
- **V1:** Periodic summary reports (markdown/PDF).
- **V2:** Real-time dashboards showing velocity, cycle time, sub-agent ROI, and task throughput across the organization.

### 10. Native Voice Command Interface
- **V1:** Command-line and Web UI interaction.
- **V2:** Integration with `openclaw-signal-voice` or similar to allow for voice-driven status updates and task creation.
