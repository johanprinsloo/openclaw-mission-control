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
      <span>WS: Connected</span>
      <span class="flex-1" />
      <span>v0.1.0</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useOrgStore } from '../stores/orgs'
import OrgSwitcher from '../components/OrgSwitcher.vue'

const route = useRoute()
const orgStore = useOrgStore()

const orgSlug = computed(() => route.params.orgSlug as string)

watch(orgSlug, (slug) => {
  if (slug && slug !== orgStore.activeOrg?.slug) {
    orgStore.selectOrg(slug)
  }
}, { immediate: true })

const navItems = [
  { to: 'projects', label: 'Projects', icon: 'mdi-view-dashboard-outline' },
  { to: 'tasks', label: 'Tasks', icon: 'mdi-checkbox-marked-outline' },
  { to: 'settings', label: 'Settings', icon: 'mdi-cog-outline' },
]
</script>
