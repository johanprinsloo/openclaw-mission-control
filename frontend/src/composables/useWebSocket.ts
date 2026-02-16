import { ref } from 'vue'
import { useChannelStore } from '../stores/channels'

export type WSStatus = 'disconnected' | 'connected' | 'reconnecting' | 'auth_revoked'

const wsStatus = ref<WSStatus>('disconnected')
let ws: WebSocket | null = null
let reconnectAttempts = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let currentOrgSlug: string | null = null
// Typing indicator debounce timers: channelId -> timer
const typingTimers: Record<string, ReturnType<typeof setTimeout>> = {}

export function useWebSocket() {
  const channelStore = useChannelStore()

  function connect(orgSlug: string) {
    disconnect()
    currentOrgSlug = orgSlug
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/api/v1/orgs/${orgSlug}/channels/ws`
    ws = new WebSocket(url)

    ws.onopen = () => {
      wsStatus.value = 'connected'
      reconnectAttempts = 0
      startHeartbeat()

      // Flush queued messages
      if (currentOrgSlug) {
        channelStore.flushOutboundQueue(currentOrgSlug)
      }

      // Re-subscribe to channels
      const channelIds = channelStore.channels.map(c => c.id)
      if (channelIds.length > 0) {
        send({ type: 'subscribe', channel_ids: channelIds })
      }
    }

    ws.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data)
        handleFrame(frame)
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = (event) => {
      stopHeartbeat()
      if (event.code === 4001) {
        wsStatus.value = 'auth_revoked'
        return
      }
      wsStatus.value = 'reconnecting'
      scheduleReconnect(orgSlug)
    }

    ws.onerror = () => {
      // onerror is always followed by onclose
    }
  }

  function handleFrame(frame: any) {
    switch (frame.type) {
      case 'message':
        channelStore.receiveMessage(frame)
        // Clear typing indicator for the sender
        channelStore.clearTypingIndicator(frame.channel_id, frame.sender_id)
        break
      case 'typing':
        channelStore.setTypingIndicator(
          frame.channel_id,
          frame.sender_id,
          frame.sender_display_name ?? '',
          true
        )
        // Auto-clear after 3 seconds
        clearTimeout(typingTimers[`${frame.channel_id}:${frame.sender_id}`])
        typingTimers[`${frame.channel_id}:${frame.sender_id}`] = setTimeout(() => {
          channelStore.clearTypingIndicator(frame.channel_id, frame.sender_id)
        }, 3000)
        break
      case 'typing_stopped':
        channelStore.clearTypingIndicator(frame.channel_id, frame.sender_id)
        break
      case 'pong':
        break
      case 'subscribed':
        break
    }
  }

  function send(frame: any) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(frame))
    }
  }

  function sendTyping(channelId: string) {
    send({ type: 'typing', channel_id: channelId })
  }

  function sendTypingStopped(channelId: string) {
    send({ type: 'typing_stopped', channel_id: channelId })
  }

  function subscribeChannels(channelIds: string[]) {
    send({ type: 'subscribe', channel_ids: channelIds })
  }

  function startHeartbeat() {
    heartbeatTimer = setInterval(() => {
      send({ type: 'ping' })
    }, 30000)
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function scheduleReconnect(orgSlug: string) {
    const delay = Math.min(1000 * 2 ** reconnectAttempts, 30000)
    reconnectAttempts++
    reconnectTimer = setTimeout(() => connect(orgSlug), delay)
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    stopHeartbeat()
    ws?.close()
    ws = null
    wsStatus.value = 'disconnected'
  }

  const isConnected = () => wsStatus.value === 'connected'

  return {
    wsStatus,
    connect,
    disconnect,
    send,
    sendTyping,
    sendTypingStopped,
    subscribeChannels,
    isConnected,
  }
}
