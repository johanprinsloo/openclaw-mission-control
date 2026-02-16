import { ref } from 'vue'
import { useProjectStore } from '../stores/projects'

export type SSEStatus = 'disconnected' | 'connected' | 'reconnecting'

const sseStatus = ref<SSEStatus>('disconnected')
let eventSource: EventSource | null = null
let reconnectAttempts = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

export function useSSE() {
  const projectStore = useProjectStore()

  function connect(orgSlug: string) {
    disconnect()
    const url = `/api/v1/orgs/${orgSlug}/events/stream`
    eventSource = new EventSource(url, { withCredentials: true })

    eventSource.onopen = () => {
      sseStatus.value = 'connected'
      reconnectAttempts = 0
    }

    eventSource.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data)
        dispatch(parsed)
      } catch {
        // ignore parse errors
      }
    }

    eventSource.onerror = () => {
      sseStatus.value = 'reconnecting'
      eventSource?.close()
      eventSource = null
      scheduleReconnect(orgSlug)
    }
  }

  function dispatch(event: { type: string; payload: any }) {
    const prefix = event.type.split('.')[0]
    if (prefix === 'project') {
      projectStore.handleEvent(event)
    }
  }

  function scheduleReconnect(orgSlug: string) {
    const delay = Math.min(1000 * 2 ** reconnectAttempts, 60000)
    reconnectAttempts++
    reconnectTimer = setTimeout(() => connect(orgSlug), delay)
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    eventSource?.close()
    eventSource = null
    sseStatus.value = 'disconnected'
  }

  return { sseStatus, connect, disconnect }
}
