<template>
  <div class="min-h-screen flex items-center justify-center"
       style="background: var(--surface-primary);">
    <div class="w-full max-w-lg">
      <h1 class="text-2xl font-semibold mb-6 text-center"
          style="color: var(--text-primary);">Select Organization</h1>

      <v-card variant="elevated" class="mb-4">
        <v-list v-if="orgStore.orgs.length > 0">
          <v-list-item
            v-for="org in orgStore.orgs" :key="org.id"
            :to="`/orgs/${org.slug}`"
            class="py-3">
            <template v-slot:prepend>
              <v-icon color="primary">mdi-domain</v-icon>
            </template>
            <v-list-item-title class="font-medium">{{ org.name }}</v-list-item-title>
            <v-list-item-subtitle>{{ org.slug }} · {{ org.status }}</v-list-item-subtitle>
            <template v-slot:append>
              <v-chip size="small" variant="tonal">{{ org.role }}</v-chip>
            </template>
          </v-list-item>
        </v-list>
        <v-card-text v-else-if="!orgStore.loading" class="text-center py-8"
                     style="color: var(--text-secondary);">
          No organizations yet. Create one to get started.
        </v-card-text>
        <v-card-text v-else class="text-center py-8">
          <v-progress-circular indeterminate color="primary" />
        </v-card-text>
      </v-card>

      <!-- Create Org -->
      <v-card variant="outlined">
        <v-card-title class="text-base">Create New Organization</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="newName" label="Name" density="compact"
            variant="outlined" class="mb-2" />
          <v-text-field
            v-model="newSlug" label="Slug" density="compact"
            variant="outlined" hint="Lowercase, hyphens allowed (e.g., acme-robotics)" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" variant="flat" :loading="creating"
                 :disabled="!newName || !newSlug"
                 @click="handleCreate">
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useOrgStore } from '../stores/orgs'

const router = useRouter()
const orgStore = useOrgStore()

const newName = ref('')
const newSlug = ref('')
const creating = ref(false)

onMounted(() => {
  orgStore.fetchOrgs()
})

async function handleCreate() {
  creating.value = true
  try {
    const org = await orgStore.create(newName.value, newSlug.value)
    router.push(`/orgs/${org.slug}`)
  } catch (e: any) {
    alert(e.response?.data?.detail ?? e.message)
  } finally {
    creating.value = false
  }
}
</script>
