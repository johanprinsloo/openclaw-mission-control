import api from './client'

export interface OrgListItem {
  id: string
  name: string
  slug: string
  status: string
  role: string
}

export interface OrgSettings {
  authentication: {
    allowed_oidc_providers: string[]
    api_key_rotation_reminder_days: number
  }
  task_defaults: {
    default_required_evidence_types: string[]
    default_priority: string
  }
  notifications: {
    enabled_channels: string[]
    default_channel: string | null
    email_from_address: string | null
  }
  integrations: {
    github: { enabled: boolean; org_name: string | null }
    google_workspace: { enabled: boolean; domain: string | null }
  }
  agent_limits: {
    max_concurrent_sub_agents: number | null
    allowed_models: string[]
    sub_agent_default_timeout_minutes: number
  }
  backup: {
    enabled: boolean
    schedule_cron: string | null
    destination: string | null
    retention_days: number
  }
  deletion_grace_period_days: number
}

export interface OrgDetail {
  id: string
  name: string
  slug: string
  status: string
  settings: OrgSettings
  created_at: string
  updated_at: string
  deletion_scheduled_at: string | null
}

export async function listOrgs(): Promise<OrgListItem[]> {
  const { data } = await api.get('/orgs')
  return data.data
}

export async function createOrg(name: string, slug: string): Promise<OrgDetail> {
  const { data } = await api.post('/orgs', { name, slug })
  return data
}

export async function getOrg(orgSlug: string): Promise<OrgDetail> {
  const { data } = await api.get(`/orgs/${orgSlug}`)
  return data
}

export async function updateOrg(
  orgSlug: string,
  patch: { name?: string; settings?: Record<string, any> }
): Promise<OrgDetail> {
  const { data } = await api.patch(`/orgs/${orgSlug}`, patch)
  return data
}

export async function deleteOrg(orgSlug: string): Promise<void> {
  await api.delete(`/orgs/${orgSlug}`)
}

export async function reactivateOrg(orgSlug: string): Promise<OrgDetail> {
  const { data } = await api.post(`/orgs/${orgSlug}/reactivate`)
  return data
}
