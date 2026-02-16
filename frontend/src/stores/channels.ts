import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  listChannels,
  getMessages,
  postMessage,
  type ChannelInfo,
  type MessageInfo,
} from '../api/channels'

let _clientIdCounter = 0
function nextClientId(): string {
  return `client_${Date.now()}_${++_clientIdCounter}`
}

export const useChannelStore = defineStore('channels', () => {
  // State
  const channels = ref<ChannelInfo[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Per-channel message state
  const messagesByChannel = ref<Record<string, MessageInfo[]>>({})
  const paginationByChannel = ref<Record<string, { nextCursor: string | null; hasMore: boolean }>>({})
  const loadingMessages = ref<Record<string, boolean>>({})

  // Typing indicators: channelId -> { userId: displayName }
  const typingByChannel = ref<Record<string, Record<string, string>>>({})

  // Outbound queue for offline messages
  const outboundQueue = ref<Array<{ channelId: string; content: string; mentions: string[]; clientId: string }>>([])

  // Unread tracking: channelId -> count
  const unreadByChannel = ref<Record<string, number>>({})

  // Active channel
  const activeChannelId = ref<string | null>(null)

  // Derived
  const orgWideChannels = computed(() =>
    channels.value.filter(c => c.type === 'org_wide')
  )
  const projectChannels = computed(() =>
    channels.value.filter(c => c.type === 'project')
  )
  const activeChannel = computed(() =>
    channels.value.find(c => c.id === activeChannelId.value) ?? null
  )

  // Actions
  async function fetchChannels(orgSlug: string) {
    loading.value = true
    error.value = null
    try {
      channels.value = await listChannels(orgSlug)
    } catch (e: any) {
      error.value = e.response?.data?.detail ?? e.message
    } finally {
      loading.value = false
    }
  }

  async function fetchMessages(orgSlug: string, channelId: string, opts?: { cursor?: string; after?: string }) {
    loadingMessages.value[channelId] = true
    try {
      const result = await getMessages(orgSlug, channelId, {
        cursor: opts?.cursor,
        after: opts?.after,
        limit: 50,
      })

      const existing = messagesByChannel.value[channelId] ?? []

      if (opts?.after) {
        // Catch-up: append newer messages
        const existingIds = new Set(existing.map(m => m.id))
        const newMessages = result.data.filter(m => !existingIds.has(m.id))
        messagesByChannel.value[channelId] = [...existing, ...newMessages]
      } else if (opts?.cursor) {
        // Loading older: prepend (result is newest-first, so reverse)
        const existingIds = new Set(existing.map(m => m.id))
        const olderMessages = result.data.filter(m => !existingIds.has(m.id))
        messagesByChannel.value[channelId] = [...olderMessages, ...existing]
      } else {
        // Initial load (newest first from API → reverse for chronological display)
        messagesByChannel.value[channelId] = [...result.data].reverse()
      }

      paginationByChannel.value[channelId] = {
        nextCursor: result.pagination.next_cursor,
        hasMore: result.pagination.has_more,
      }
    } catch (e: any) {
      error.value = e.response?.data?.detail ?? e.message
    } finally {
      loadingMessages.value[channelId] = false
    }
  }

  async function sendMessage(orgSlug: string, channelId: string, content: string, mentions: string[] = []) {
    const clientId = nextClientId()

    // Optimistic insert
    const optimistic: MessageInfo = {
      id: clientId,
      channel_id: channelId,
      sender_id: 'me', // Will be replaced by real message
      sender_display_name: null,
      sender_type: null,
      content,
      mentions,
      created_at: new Date().toISOString(),
      status: 'pending',
      client_id: clientId,
    }

    if (!messagesByChannel.value[channelId]) {
      messagesByChannel.value[channelId] = []
    }
    messagesByChannel.value[channelId].push(optimistic)

    try {
      const result = await postMessage(orgSlug, channelId, content, mentions)
      // Replace optimistic with confirmed
      const msgs = messagesByChannel.value[channelId]
      const idx = msgs.findIndex(m => m.client_id === clientId)
      if (idx !== -1) {
        msgs[idx] = { ...result, status: 'sent', client_id: clientId }
      }
    } catch (e: any) {
      // Mark as failed
      const msgs = messagesByChannel.value[channelId]
      const idx = msgs.findIndex(m => m.client_id === clientId)
      if (idx !== -1) {
        msgs[idx].status = 'failed'
      }
    }
  }

  function queueOutbound(channelId: string, content: string, mentions: string[]) {
    const clientId = nextClientId()
    outboundQueue.value.push({ channelId, content, mentions, clientId })

    // Optimistic insert
    if (!messagesByChannel.value[channelId]) {
      messagesByChannel.value[channelId] = []
    }
    messagesByChannel.value[channelId].push({
      id: clientId,
      channel_id: channelId,
      sender_id: 'me',
      sender_display_name: null,
      sender_type: null,
      content,
      mentions,
      created_at: new Date().toISOString(),
      status: 'pending',
      client_id: clientId,
    })
  }

  async function flushOutboundQueue(orgSlug: string) {
    const queue = [...outboundQueue.value]
    outboundQueue.value = []
    for (const item of queue) {
      try {
        const result = await postMessage(orgSlug, item.channelId, item.content, item.mentions)
        const msgs = messagesByChannel.value[item.channelId]
        if (msgs) {
          const idx = msgs.findIndex(m => m.client_id === item.clientId)
          if (idx !== -1) {
            msgs[idx] = { ...result, status: 'sent', client_id: item.clientId }
          }
        }
      } catch {
        const msgs = messagesByChannel.value[item.channelId]
        if (msgs) {
          const idx = msgs.findIndex(m => m.client_id === item.clientId)
          if (idx !== -1) {
            msgs[idx].status = 'failed'
          }
        }
      }
    }
  }

  function receiveMessage(frame: any) {
    const channelId = frame.channel_id
    if (!messagesByChannel.value[channelId]) {
      messagesByChannel.value[channelId] = []
    }

    const msgs = messagesByChannel.value[channelId]

    // Dedup: check if we already have this message (from optimistic insert or REST)
    if (frame.client_id) {
      const idx = msgs.findIndex(m => m.client_id === frame.client_id)
      if (idx !== -1) {
        // Replace optimistic with confirmed
        msgs[idx] = {
          id: frame.id,
          channel_id: frame.channel_id,
          sender_id: frame.sender_id,
          sender_display_name: frame.sender_display_name,
          sender_type: frame.sender_type,
          content: frame.content,
          mentions: frame.mentions ?? [],
          created_at: frame.created_at,
          status: 'sent',
          client_id: frame.client_id,
        }
        return
      }
    }

    // Check by ID
    if (msgs.some(m => m.id === frame.id)) return

    msgs.push({
      id: frame.id,
      channel_id: frame.channel_id,
      sender_id: frame.sender_id,
      sender_display_name: frame.sender_display_name,
      sender_type: frame.sender_type,
      content: frame.content,
      mentions: frame.mentions ?? [],
      created_at: frame.created_at,
      status: 'sent',
    })

    // Unread indicator (if not the active channel)
    if (channelId !== activeChannelId.value) {
      unreadByChannel.value[channelId] = (unreadByChannel.value[channelId] ?? 0) + 1
    }
  }

  function setTypingIndicator(channelId: string, senderId: string, displayName: string, isTyping: boolean) {
    if (!typingByChannel.value[channelId]) {
      typingByChannel.value[channelId] = {}
    }
    if (isTyping) {
      typingByChannel.value[channelId][senderId] = displayName || senderId.slice(0, 8)
    } else {
      delete typingByChannel.value[channelId][senderId]
    }
  }

  function setActiveChannel(channelId: string | null) {
    activeChannelId.value = channelId
    if (channelId) {
      unreadByChannel.value[channelId] = 0
    }
  }

  function clearTypingIndicator(channelId: string, senderId: string) {
    if (typingByChannel.value[channelId]) {
      delete typingByChannel.value[channelId][senderId]
    }
  }

  return {
    channels,
    loading,
    error,
    messagesByChannel,
    paginationByChannel,
    loadingMessages,
    typingByChannel,
    outboundQueue,
    unreadByChannel,
    activeChannelId,
    orgWideChannels,
    projectChannels,
    activeChannel,
    fetchChannels,
    fetchMessages,
    sendMessage,
    queueOutbound,
    flushOutboundQueue,
    receiveMessage,
    setTypingIndicator,
    setActiveChannel,
    clearTypingIndicator,
  }
})
