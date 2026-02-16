import api from './client'

export interface ChannelInfo {
  id: string
  name: string
  type: 'org_wide' | 'project'
  project_id: string | null
  created_at: string
  member_count: number
}

export interface MessageInfo {
  id: string
  channel_id: string
  sender_id: string
  sender_display_name: string | null
  sender_type: 'human' | 'agent' | null
  content: string
  mentions: string[]
  created_at: string
  // Client-side fields
  status?: 'sent' | 'pending' | 'failed'
  client_id?: string
}

export interface MessagePagination {
  next_cursor: string | null
  has_more: boolean
  limit: number
}

export async function listChannels(orgSlug: string): Promise<ChannelInfo[]> {
  const { data } = await api.get(`/orgs/${orgSlug}/channels`)
  return data.data
}

export async function getChannel(orgSlug: string, channelId: string): Promise<ChannelInfo> {
  const { data } = await api.get(`/orgs/${orgSlug}/channels/${channelId}`)
  return data
}

export async function getMessages(
  orgSlug: string,
  channelId: string,
  opts?: { cursor?: string; limit?: number; after?: string }
): Promise<{ data: MessageInfo[]; pagination: MessagePagination }> {
  const params: Record<string, string | number> = {}
  if (opts?.cursor) params.cursor = opts.cursor
  if (opts?.limit) params.limit = opts.limit
  if (opts?.after) params.after = opts.after
  const { data } = await api.get(`/orgs/${orgSlug}/channels/${channelId}/messages`, { params })
  return data
}

export async function postMessage(
  orgSlug: string,
  channelId: string,
  content: string,
  mentions: string[] = []
): Promise<MessageInfo> {
  const { data } = await api.post(`/orgs/${orgSlug}/channels/${channelId}/messages`, {
    content,
    mentions,
  })
  return data
}
