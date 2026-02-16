import api from './client'

export interface UserInfo {
  id: string
  type: 'human' | 'agent'
  email: string | null
  identifier: string | null
  display_name: string
  role: 'administrator' | 'contributor'
  has_api_key: boolean
  last_active: string | null
  created_at: string
}

export interface UserAddPayload {
  type: 'human' | 'agent'
  email?: string
  identifier?: string
  display_name: string
  role: 'administrator' | 'contributor'
}

export interface UserAddResult {
  user: UserInfo
  api_key: string | null
}

export interface ApiKeyRotateResult {
  api_key: string
  previous_key_expires_at: string
}

export async function listUsers(orgSlug: string): Promise<UserInfo[]> {
  const { data } = await api.get(`/orgs/${orgSlug}/users`)
  return data.data
}

export async function addUser(orgSlug: string, payload: UserAddPayload): Promise<UserAddResult> {
  const { data } = await api.post(`/orgs/${orgSlug}/users`, payload)
  return data
}

export async function getUser(orgSlug: string, userId: string): Promise<UserInfo> {
  const { data } = await api.get(`/orgs/${orgSlug}/users/${userId}`)
  return data
}

export async function updateUser(
  orgSlug: string,
  userId: string,
  patch: { role?: string; display_name?: string }
): Promise<UserInfo> {
  const { data } = await api.patch(`/orgs/${orgSlug}/users/${userId}`, patch)
  return data
}

export async function removeUser(orgSlug: string, userId: string): Promise<void> {
  await api.delete(`/orgs/${orgSlug}/users/${userId}`)
}

export async function rotateApiKey(orgSlug: string, userId: string): Promise<ApiKeyRotateResult> {
  const { data } = await api.post(`/orgs/${orgSlug}/users/${userId}/rotate-key`)
  return data
}

export async function revokeApiKey(orgSlug: string, userId: string): Promise<void> {
  await api.post(`/orgs/${orgSlug}/users/${userId}/revoke-key`)
}
