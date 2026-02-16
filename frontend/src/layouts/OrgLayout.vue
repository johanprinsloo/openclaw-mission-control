<template>
  <div class="flex flex-col h-screen">
    <!-- Top Bar -->
    <header class="h-14 flex items-center px-4 border-b"
            style="background: var(--surface-elevated); border-color: var(--border-default);">
      <OrgSwitcher />
      <div class="flex-1" />
      <v-btn icon size="small" variant="text">
        <v-icon>mdi-magnify</v-icon>
      </v-btn>
      <v-btn icon size="small" variant="text">
        <v-icon>mdi-bell-outline</v-icon>
      </v-btn>
    </header>

    <div class="flex flex-1 overflow-hidden">
      <!-- Sidebar -->
      <nav class="w-56 flex-shrink-0 border-r overflow-y-auto py-3 px-2"
           style="background: var(--surface-secondary); border-color: var(--border-default);">
        <div class="text-xs font-semibold uppercase tracking-wider mb-2 px-2"
             style="color: var(--text-tertiary);">Navigation</div>
        <router-link
          v-for="item in navItems" :key="item.to"
          :to="`/orgs/${orgSlug}/${item.to}`"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm hover:bg-white/50 transition"
          :class="{ 'bg-white/70 font-medium': $route.path.includes(item.to) }"
          style="color: var(--text-primary);">
          <v-icon size="18">{{ item.icon }}</v-icon>
          {{ item.label }}
        </router-link>

        <!-- Channel List -->
        <template v-if="channelStore.orgWideChannels.length > 0">
          <div class="text-xs font-semibold uppercase tracking-wider mt-4 mb-2 px-2"
               style="color: var(--text-tertiary);">Channels</div>
          <router-link
            v-for="ch in channelStore.orgWideChannels" :key="ch.id"
            :to="`/orgs/${orgSlug}/channels/${ch.id}`"
            class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm hover:bg-white/50 transition"
            :class="{ 'bg-white/70 font-medium': $route.params.id === ch.id }"
            style="color: var(--text-primary);">
            <v-icon size="16">mdi-pound</v-icon>
            <span class="truncate flex-1">{{ ch.name }}</span>
            <span v-if="channelStore.unreadByChannel[ch.id]"
                  class="w-5 h-5 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center">
              {{ channelStore.unreadByChannel[ch.id] > 9 ? '9+' : channelStore.unreadByChannel[ch.id] }}
            </span>
          </router-link>
        </template>

        <template v-if="channelStore.projectChannels.length > 0">
          <div class="text-xs font-semibold uppercase tracking-wider mt-4 mb-2 px-2"
               style="color: var(--text-tertiary);">Project Channels</div>
          <router-link
            v-for="ch in channelStore.projectChannels" :key="ch.id"
            :to="`/orgs/${orgSlug}/channels/${ch.id}`"
            class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm hover:bg-white/50 transition"
            :class="{ 'bg-white/70 font-medium': $route.params.id === ch.id }"
            style="color: var(--text-primary);">
            <v-icon size="16">mdi-pound</v-icon>
            <span class="truncate flex-1">{{ ch.name }}</span>
            <span v-if="channelStore.unreadByChannel[ch.id]"
                  class="w-5 h-5 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center">
              {{ channelStore.unreadByChannel[ch.id] > 9 ? '9+' : channelStore.unreadByChannel[ch.id] }}
            </span>
          </router-link>
        </template>
      </nav>

      <!-- Main Content -->
      <main class="flex-1 overflow-y-auto p-6">
        <router-view />
      </main>
    </div>

    <!-- Status Bar -->
    <footer class="h-7 flex items-center px-4 text-xs border-t"
            style="background: var(--surface-secondary); border-color: var(--border-default); color: var(--text-tertiary);">
      <span>SSE: Connected</span>
      <span class="mx-3">•</span>
      <span :style="{ color: wsStatus === 'connected' ? 'var(--text-tertiary)' : wsStatus === 'reconnecting' ? '#f59e0b' : '#ef4444' }">
        WS: {{ wsStatus }}
      </span>
      <span class="flex-1" />
      <span>v0.1.0</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useOrgStore } from '../stores/orgs'
import { useChannelStore } from '../stores/channels'
import { useWebSocket } from '../composables/useWebSocket'
import OrgSwitcher from '../components/OrgSwitcher.vue'

const route = useRoute()
const orgStore = useOrgStore()

const channelStore = useChannelStore()
const { wsStatus, connect: wsConnect, disconnect: wsDisconnect } = useWebSocket()

const orgSlug = computed(() => route.params.orgSlug as string)

watch(orgSlug, (slug) => {
  if (slug && slug !== orgStore.activeOrg?.slug) {
    orgStore.selectOrg(slug)
  }
  if (slug) {
    channelStore.fetchChannels(slug)
    wsConnect(slug)
  }
}, { immediate: true })

onUnmounted(() => {
  wsDisconnect()
})

const navItems = [
  { to: 'projects', label: 'Projects', icon: 'mdi-view-dashboard-outline' },
  { to: 'tasks', label: 'Tasks', icon: 'mdi-checkbox-marked-outline' },
  { to: 'settings/users', label: 'Users', icon: 'mdi-account-group-outline' },
  { to: 'settings', label: 'Settings', icon: 'mdi-cog-outline' },
]
</script>
