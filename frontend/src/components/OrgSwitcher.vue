<template>
  <v-menu>
    <template v-slot:activator="{ props }">
      <v-btn variant="text" v-bind="props" class="text-none font-medium">
        <v-icon start>mdi-domain</v-icon>
        {{ orgStore.activeOrg?.name ?? 'Select Org' }}
        <v-icon end>mdi-chevron-down</v-icon>
      </v-btn>
    </template>
    <v-list density="compact">
      <v-list-item
        v-for="org in orgStore.orgs" :key="org.id"
        :value="org.slug"
        @click="switchOrg(org.slug)"
        :active="org.slug === orgStore.activeOrgSlug">
        <v-list-item-title>{{ org.name }}</v-list-item-title>
        <template v-slot:append>
          <v-chip size="x-small" variant="outlined">{{ org.role }}</v-chip>
        </template>
      </v-list-item>
      <v-divider class="my-1" />
      <v-list-item @click="$router.push('/orgs')">
        <v-list-item-title class="text-sm" style="color: var(--text-secondary);">
          All Organizations
        </v-list-item-title>
      </v-list-item>
    </v-list>
  </v-menu>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useOrgStore } from '../stores/orgs'

const router = useRouter()
const orgStore = useOrgStore()

onMounted(() => {
  orgStore.fetchOrgs()
})

function switchOrg(slug: string) {
  router.push(`/orgs/${slug}`)
}
</script>
