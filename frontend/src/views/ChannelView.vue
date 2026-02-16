<template>
  <div class="flex flex-col h-full" style="max-height: calc(100vh - 7rem);">
    <!-- Channel Header -->
    <div class="flex items-center gap-2 px-4 py-3 border-b flex-shrink-0"
         style="border-color: var(--border-default);">
      <v-icon size="20" color="grey">mdi-pound</v-icon>
      <span class="font-semibold" style="color: var(--text-primary);">
        {{ channel?.name ?? 'Loading...' }}
      </span>
      <v-chip v-if="channel?.type === 'project'" size="x-small" color="primary" variant="outlined">
        Project
      </v-chip>
      <div class="flex-1" />
      <span class="text-xs" style="color: var(--text-tertiary);">
        {{ channel?.member_count ?? 0 }} members
      </span>
    </div>

    <!-- Messages Area -->
    <div ref="messagesContainer"
         class="flex-1 overflow-y-auto px-4 py-2"
         @scroll="onScroll">
      <!-- Load More Indicator -->
      <div v-if="hasMore" class="text-center py-2">
        <v-btn v-if="!loadingOlder" size="small" variant="text" @click="loadOlder">
          Load older messages
        </v-btn>
        <v-progress-circular v-else indeterminate size="20" width="2" />
      </div>

      <!-- Messages -->
      <div v-for="(msg, idx) in messages" :key="msg.id"
           class="mb-3">
        <!-- Date separator -->
        <div v-if="shouldShowDateSeparator(idx)"
             class="text-center my-4">
          <span class="text-xs px-3 py-1 rounded-full"
                style="background: var(--surface-secondary); color: var(--text-tertiary);">
            {{ formatDateSeparator(msg.created_at) }}
          </span>
        </div>

        <!-- Message bubble -->
        <div class="flex items-start gap-2" :class="{ 'opacity-60': msg.status === 'pending' }">
          <!-- Avatar -->
          <div class="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-semibold"
               :style="{ background: avatarColor(msg.sender_id), color: '#fff' }">
            {{ avatarInitials(msg.sender_display_name ?? msg.sender_id) }}
          </div>

          <div class="flex-1 min-w-0">
            <!-- Sender + timestamp -->
            <div class="flex items-center gap-2 mb-0.5">
              <span class="text-sm font-semibold" style="color: var(--text-primary);">
                {{ msg.sender_display_name ?? msg.sender_id.slice(0, 8) }}
              </span>
              <v-chip v-if="msg.sender_type === 'agent'" size="x-small" color="purple" variant="flat"
                      class="text-white">
                agent
              </v-chip>
              <span class="text-xs" style="color: var(--text-tertiary);">
                {{ formatTime(msg.created_at) }}
              </span>
              <v-icon v-if="msg.status === 'pending'" size="14" color="grey">mdi-clock-outline</v-icon>
              <v-icon v-if="msg.status === 'failed'" size="14" color="error">mdi-alert-circle-outline</v-icon>
            </div>

            <!-- Content -->
            <div class="text-sm break-words" style="color: var(--text-secondary);"
                 :class="{ 'font-mono bg-gray-100 rounded px-2 py-1 text-xs': isCommand(msg.content) }"
                 v-html="renderContent(msg.content)">
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="!loading && messages.length === 0" class="flex flex-col items-center justify-center h-full">
        <v-icon size="48" color="grey-lighten-1">mdi-message-outline</v-icon>
        <p class="mt-2 text-sm" style="color: var(--text-tertiary);">No messages yet. Start the conversation!</p>
      </div>
    </div>

    <!-- Typing Indicator -->
    <div v-if="typingText" class="px-4 py-1 text-xs" style="color: var(--text-tertiary);">
      {{ typingText }}
    </div>

    <!-- Message Input -->
    <div class="px-4 py-3 border-t flex-shrink-0" style="border-color: var(--border-default);">
      <!-- Autocomplete dropdown -->
      <div v-if="showMentionAutocomplete" class="mb-2 border rounded shadow-sm max-h-40 overflow-y-auto"
           style="background: var(--surface-elevated); border-color: var(--border-default);">
        <div v-for="(user, idx) in filteredMentionUsers" :key="user.id"
             class="px-3 py-2 text-sm cursor-pointer hover:bg-gray-100"
             :class="{ 'bg-blue-50': idx === mentionSelectedIndex }"
             @click="selectMention(user)">
          <span class="font-medium">{{ user.display_name }}</span>
          <v-chip v-if="user.type === 'agent'" size="x-small" color="purple" variant="outlined" class="ml-1">
            agent
          </v-chip>
        </div>
      </div>

      <div v-if="showCommandAutocomplete" class="mb-2 border rounded shadow-sm max-h-40 overflow-y-auto"
           style="background: var(--surface-elevated); border-color: var(--border-default);">
        <div v-for="(cmd, idx) in filteredCommands" :key="cmd"
             class="px-3 py-2 text-sm cursor-pointer hover:bg-gray-100 font-mono"
             :class="{ 'bg-blue-50': idx === commandSelectedIndex }"
             @click="selectCommand(cmd)">
          /{{ cmd }}
        </div>
      </div>

      <!-- WS disconnected warning -->
      <div v-if="wsStatus === 'reconnecting'"
           class="mb-2 px-3 py-1 rounded text-xs bg-yellow-50 text-yellow-800 flex items-center gap-1">
        <v-icon size="14">mdi-wifi-off</v-icon>
        Reconnecting... Messages will be queued.
      </div>

      <div class="flex items-end gap-2">
        <v-textarea
          ref="inputRef"
          v-model="inputText"
          placeholder="Type a message... @mention with @, commands with /"
          variant="outlined"
          density="compact"
          rows="1"
          max-rows="4"
          auto-grow
          hide-details
          @keydown="onKeydown"
          @input="onInput"
        />
        <v-btn icon color="primary" size="small"
               :disabled="!inputText.trim()"
               @click="handleSend">
          <v-icon>mdi-send</v-icon>
        </v-btn>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useChannelStore } from '../stores/channels'
import { useWebSocket } from '../composables/useWebSocket'
import { listUsers, type UserInfo } from '../api/users'

const route = useRoute()
const channelStore = useChannelStore()
const { wsStatus, sendTyping, sendTypingStopped, subscribeChannels } = useWebSocket()

const orgSlug = computed(() => route.params.orgSlug as string)
const channelId = computed(() => route.params.id as string)

const inputText = ref('')
const inputRef = ref<any>(null)
const messagesContainer = ref<HTMLElement | null>(null)
const loadingOlder = ref(false)
const orgUsers = ref<UserInfo[]>([])

// Mention autocomplete
const showMentionAutocomplete = ref(false)
const mentionQuery = ref('')
const mentionSelectedIndex = ref(0)
const mentionStartPos = ref(0)

// Command autocomplete
const showCommandAutocomplete = ref(false)
const commandQuery = ref('')
const commandSelectedIndex = ref(0)
const availableCommands = ['status', 'help', 'compact', 'assign', 'unassign']

// Typing debounce
let typingTimer: ReturnType<typeof setTimeout> | null = null
let isTyping = false

const channel = computed(() =>
  channelStore.channels.find(c => c.id === channelId.value) ?? null
)

const messages = computed(() =>
  channelStore.messagesByChannel[channelId.value] ?? []
)

const loading = computed(() =>
  channelStore.loadingMessages[channelId.value] ?? false
)

const hasMore = computed(() =>
  channelStore.paginationByChannel[channelId.value]?.hasMore ?? false
)

const typingUsers = computed(() => {
  const t = channelStore.typingByChannel[channelId.value] ?? {}
  return Object.values(t)
})

const typingText = computed(() => {
  const names = typingUsers.value
  if (names.length === 0) return ''
  if (names.length === 1) return `${names[0]} is typing...`
  if (names.length === 2) return `${names[0]} and ${names[1]} are typing...`
  return `${names[0]} and ${names.length - 1} others are typing...`
})

const filteredMentionUsers = computed(() => {
  if (!mentionQuery.value) return orgUsers.value.slice(0, 10)
  const q = mentionQuery.value.toLowerCase()
  return orgUsers.value.filter(u =>
    u.display_name.toLowerCase().includes(q) ||
    (u.email?.toLowerCase().includes(q))
  ).slice(0, 10)
})

const filteredCommands = computed(() => {
  if (!commandQuery.value) return availableCommands
  return availableCommands.filter(c => c.startsWith(commandQuery.value.toLowerCase()))
})

// Load channel data
watch([orgSlug, channelId], async ([slug, cid]) => {
  if (!slug || !cid) return
  channelStore.setActiveChannel(cid)
  await channelStore.fetchMessages(slug, cid)
  subscribeChannels([cid])
  scrollToBottom()

  // Load users for mention autocomplete
  try {
    orgUsers.value = await listUsers(slug)
  } catch { /* ignore */ }
}, { immediate: true })

onMounted(() => {
  scrollToBottom()
})

onUnmounted(() => {
  channelStore.setActiveChannel(null)
  if (typingTimer) clearTimeout(typingTimer)
})

// Auto-scroll on new messages
watch(() => messages.value.length, () => {
  if (isNearBottom()) {
    nextTick(scrollToBottom)
  }
})

function isNearBottom(): boolean {
  const el = messagesContainer.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 100
}

function scrollToBottom() {
  nextTick(() => {
    const el = messagesContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function loadOlder() {
  const pagination = channelStore.paginationByChannel[channelId.value]
  if (!pagination?.nextCursor || loadingOlder.value) return
  loadingOlder.value = true

  const el = messagesContainer.value
  const prevScrollHeight = el?.scrollHeight ?? 0

  await channelStore.fetchMessages(orgSlug.value, channelId.value, {
    cursor: pagination.nextCursor,
  })

  // Maintain scroll position after prepending
  nextTick(() => {
    if (el) {
      el.scrollTop = el.scrollHeight - prevScrollHeight
    }
  })
  loadingOlder.value = false
}

function onScroll() {
  const el = messagesContainer.value
  if (!el) return
  if (el.scrollTop < 100 && hasMore.value && !loadingOlder.value) {
    loadOlder()
  }
}

function handleSend() {
  const text = inputText.value.trim()
  if (!text) return

  if (wsStatus.value === 'connected') {
    channelStore.sendMessage(orgSlug.value, channelId.value, text)
  } else {
    channelStore.queueOutbound(channelId.value, text, [])
  }

  inputText.value = ''
  showMentionAutocomplete.value = false
  showCommandAutocomplete.value = false

  // Stop typing
  if (isTyping) {
    sendTypingStopped(channelId.value)
    isTyping = false
  }
  if (typingTimer) clearTimeout(typingTimer)

  nextTick(scrollToBottom)
}

function onKeydown(e: KeyboardEvent) {
  // Send on Enter (without Shift)
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    if (showMentionAutocomplete.value && filteredMentionUsers.value.length > 0) {
      selectMention(filteredMentionUsers.value[mentionSelectedIndex.value])
      return
    }
    if (showCommandAutocomplete.value && filteredCommands.value.length > 0) {
      selectCommand(filteredCommands.value[commandSelectedIndex.value])
      return
    }
    handleSend()
    return
  }

  // Navigate autocomplete with arrow keys
  if (showMentionAutocomplete.value) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      mentionSelectedIndex.value = Math.min(mentionSelectedIndex.value + 1, filteredMentionUsers.value.length - 1)
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      mentionSelectedIndex.value = Math.max(mentionSelectedIndex.value - 1, 0)
      return
    }
    if (e.key === 'Escape') {
      showMentionAutocomplete.value = false
      return
    }
    if (e.key === 'Tab') {
      e.preventDefault()
      if (filteredMentionUsers.value.length > 0) {
        selectMention(filteredMentionUsers.value[mentionSelectedIndex.value])
      }
      return
    }
  }

  if (showCommandAutocomplete.value) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      commandSelectedIndex.value = Math.min(commandSelectedIndex.value + 1, filteredCommands.value.length - 1)
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      commandSelectedIndex.value = Math.max(commandSelectedIndex.value - 1, 0)
      return
    }
    if (e.key === 'Escape') {
      showCommandAutocomplete.value = false
      return
    }
    if (e.key === 'Tab') {
      e.preventDefault()
      if (filteredCommands.value.length > 0) {
        selectCommand(filteredCommands.value[commandSelectedIndex.value])
      }
      return
    }
  }
}

function onInput() {
  // Typing indicator
  if (!isTyping && inputText.value.trim()) {
    isTyping = true
    sendTyping(channelId.value)
  }
  if (typingTimer) clearTimeout(typingTimer)
  typingTimer = setTimeout(() => {
    if (isTyping) {
      sendTypingStopped(channelId.value)
      isTyping = false
    }
  }, 3000)

  // Mention autocomplete detection
  const text = inputText.value
  const lastAtIdx = text.lastIndexOf('@')
  if (lastAtIdx >= 0 && (lastAtIdx === 0 || text[lastAtIdx - 1] === ' ')) {
    const afterAt = text.substring(lastAtIdx + 1)
    if (!afterAt.includes(' ')) {
      mentionQuery.value = afterAt
      mentionStartPos.value = lastAtIdx
      mentionSelectedIndex.value = 0
      showMentionAutocomplete.value = true
      showCommandAutocomplete.value = false
      return
    }
  }
  showMentionAutocomplete.value = false

  // Command autocomplete detection
  if (text.startsWith('/') && !text.includes(' ')) {
    commandQuery.value = text.substring(1)
    commandSelectedIndex.value = 0
    showCommandAutocomplete.value = true
    showMentionAutocomplete.value = false
    return
  }
  showCommandAutocomplete.value = false
}

function selectMention(user: UserInfo) {
  const before = inputText.value.substring(0, mentionStartPos.value)
  inputText.value = `${before}@${user.id} `
  showMentionAutocomplete.value = false
  inputRef.value?.focus()
}

function selectCommand(cmd: string) {
  inputText.value = `/${cmd} `
  showCommandAutocomplete.value = false
  inputRef.value?.focus()
}

// Rendering helpers
function renderContent(content: string): string {
  // Escape HTML
  let escaped = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Highlight mentions
  escaped = escaped.replace(
    /@([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/gi,
    (_, uuid) => {
      const user = orgUsers.value.find(u => u.id === uuid)
      const name = user?.display_name ?? uuid.slice(0, 8)
      return `<span class="mention-highlight" style="background: #e3f2fd; color: #1565c0; padding: 0 2px; border-radius: 3px; font-weight: 500;">@${name}</span>`
    }
  )

  return escaped
}

function isCommand(content: string): boolean {
  return content.trim().startsWith('/')
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)

  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`

  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatDateSeparator(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) return 'Today'
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })
}

function shouldShowDateSeparator(idx: number): boolean {
  if (idx === 0) return true
  const prev = messages.value[idx - 1]
  const curr = messages.value[idx]
  return new Date(prev.created_at).toDateString() !== new Date(curr.created_at).toDateString()
}

function avatarColor(id: string): string {
  const colors = ['#1976D2', '#388E3C', '#D32F2F', '#7B1FA2', '#F57C00', '#0097A7', '#5D4037', '#455A64']
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = id.charCodeAt(i) + ((hash << 5) - hash)
  return colors[Math.abs(hash) % colors.length]
}

function avatarInitials(name: string): string {
  if (!name) return '?'
  const parts = name.split(/[@.\s]/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.substring(0, 2).toUpperCase()
}
</script>
