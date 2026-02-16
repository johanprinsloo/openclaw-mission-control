import api from './client'

export interface Project {
  id: string
  org_id: string
  name: string
  type: string
  description: string | null
  stage: string
  owner_id: string | null
  links: Record<string, string>
  task_count: number
  task_complete_count: number
  created_at: string
  updated_at: string
}

export async function listProjects(orgSlug: string, params?: { stage?: string; owner_id?: string }): Promise<Project[]> {
  const { data } = await api.get(`/orgs/${orgSlug}/projects`, { params })
  return data
}

export async function createProject(orgSlug: string, body: {
  name: string
  type: string
  description?: string
  owner_id?: string
}): Promise<Project> {
  const { data } = await api.post(`/orgs/${orgSlug}/projects`, body)
  return data
}

export async function getProject(orgSlug: string, projectId: string): Promise<Project> {
  const { data } = await api.get(`/orgs/${orgSlug}/projects/${projectId}`)
  return data
}

export async function updateProject(orgSlug: string, projectId: string, body: Partial<{
  name: string
  description: string
  type: string
  links: Record<string, string>
  owner_id: string
}>): Promise<Project> {
  const { data } = await api.patch(`/orgs/${orgSlug}/projects/${projectId}`, body)
  return data
}

export async function transitionProject(orgSlug: string, projectId: string, toStage: string): Promise<Project> {
  const { data } = await api.post(`/orgs/${orgSlug}/projects/${projectId}/transition`, { to_stage: toStage })
  return data
}

export async function deleteProject(orgSlug: string, projectId: string): Promise<void> {
  await api.delete(`/orgs/${orgSlug}/projects/${projectId}`)
}

export async function addProjectMembers(orgSlug: string, projectId: string, userIds: string[]): Promise<void> {
  await api.post(`/orgs/${orgSlug}/projects/${projectId}/members`, { user_ids: userIds })
}

export async function removeProjectMember(orgSlug: string, projectId: string, userId: string): Promise<void> {
  await api.delete(`/orgs/${orgSlug}/projects/${projectId}/members/${userId}`)
}
