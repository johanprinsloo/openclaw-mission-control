import api from './client'

export interface Evidence {
  id: string
  task_id: string
  type: string
  url: string
  submitted_at: string
  submitted_by: string
}

export interface Task {
  id: string
  org_id: string
  title: string
  description: string | null
  type: string
  priority: string
  status: string
  required_evidence_types: string[]
  project_ids: string[]
  assignee_ids: string[]
  dependency_ids: string[]
  evidence: Evidence[]
  completed_at: string | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface TaskFilters {
  project_id?: string
  status?: string
  assignee_id?: string
  priority?: string
  page?: number
  per_page?: number
}

export interface EvidenceSubmission {
  type: string
  url: string
}

export async function listTasks(orgSlug: string, filters?: TaskFilters): Promise<Task[]> {
  const { data } = await api.get(`/orgs/${orgSlug}/tasks`, { params: filters })
  return data
}

export async function createTask(orgSlug: string, body: {
  title: string
  description?: string
  type?: string
  priority?: string
  required_evidence_types?: string[]
  project_ids?: string[]
  assignee_ids?: string[]
}): Promise<Task> {
  const { data } = await api.post(`/orgs/${orgSlug}/tasks`, body)
  return data
}

export async function getTask(orgSlug: string, taskId: string): Promise<Task> {
  const { data } = await api.get(`/orgs/${orgSlug}/tasks/${taskId}`)
  return data
}

export async function updateTask(orgSlug: string, taskId: string, body: Partial<{
  title: string
  description: string
  type: string
  priority: string
  required_evidence_types: string[]
  project_ids: string[]
  assignee_ids: string[]
}>): Promise<Task> {
  const { data } = await api.patch(`/orgs/${orgSlug}/tasks/${taskId}`, body)
  return data
}

export async function transitionTask(orgSlug: string, taskId: string, body: {
  to_status: string
  evidence?: EvidenceSubmission[]
}): Promise<Task> {
  const { data } = await api.post(`/orgs/${orgSlug}/tasks/${taskId}/transition`, body)
  return data
}

export async function addDependency(orgSlug: string, taskId: string, blockedById: string): Promise<void> {
  await api.post(`/orgs/${orgSlug}/tasks/${taskId}/dependencies`, { blocked_by_id: blockedById })
}

export async function removeDependency(orgSlug: string, taskId: string, blockedById: string): Promise<void> {
  await api.delete(`/orgs/${orgSlug}/tasks/${taskId}/dependencies/${blockedById}`)
}
