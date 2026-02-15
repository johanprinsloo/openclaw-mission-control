<template>
  <div>
    <h2 class="text-xl font-semibold mb-4">Organization Settings</h2>

    <v-alert v-if="orgStore.activeOrg?.status === 'pending_deletion'"
             type="warning" variant="tonal" class="mb-4">
      This organization is scheduled for deletion on
      {{ orgStore.activeOrg.deletion_scheduled_at }}.
      <v-btn variant="text" size="small" @click="orgStore.cancelDeletion()">
        Cancel Deletion
      </v-btn>
    </v-alert>

    <v-card v-if="orgStore.activeOrg" variant="elevated">
      <v-tabs v-model="tab" color="primary">
        <v-tab value="general">General</v-tab>
        <v-tab value="auth">Authentication</v-tab>
        <v-tab value="defaults">Task Defaults</v-tab>
        <v-tab value="integrations">Integrations</v-tab>
        <v-tab value="agents">Agent Limits</v-tab>
        <v-tab value="danger">Danger Zone</v-tab>
      </v-tabs>

      <v-card-text>
        <v-tabs-window v-model="tab">
          <!-- General -->
          <v-tabs-window-item value="general">
            <v-text-field v-model="form.name" label="Organization Name"
                          variant="outlined" density="compact" class="mb-3" />
            <v-btn color="primary" variant="flat" @click="saveName" :loading="saving">
              Save Name
            </v-btn>
          </v-tabs-window-item>

          <!-- Authentication -->
          <v-tabs-window-item value="auth">
            <v-select
              v-model="settings.authentication.allowed_oidc_providers"
              :items="['github', 'google']" label="Allowed OIDC Providers"
              variant="outlined" density="compact" multiple chips class="mb-3" />
            <v-text-field
              v-model.number="settings.authentication.api_key_rotation_reminder_days"
              label="API Key Rotation Reminder (days)" type="number"
              variant="outlined" density="compact" class="mb-3" />
            <v-btn color="primary" variant="flat" @click="saveSettings" :loading="saving">
              Save
            </v-btn>
          </v-tabs-window-item>

          <!-- Task Defaults -->
          <v-tabs-window-item value="defaults">
            <v-select
              v-model="settings.task_defaults.default_priority"
              :items="['low', 'medium', 'high', 'critical']"
              label="Default Priority"
              variant="outlined" density="compact" class="mb-3" />
            <v-select
              v-model="settings.task_defaults.default_required_evidence_types"
              :items="['pr_link', 'test_results', 'doc_url']"
              label="Default Required Evidence"
              variant="outlined" density="compact" multiple chips class="mb-3" />
            <v-btn color="primary" variant="flat" @click="saveSettings" :loading="saving">
              Save
            </v-btn>
          </v-tabs-window-item>

          <!-- Integrations -->
          <v-tabs-window-item value="integrations">
            <div class="mb-4">
              <h3 class="text-base font-medium mb-2">GitHub</h3>
              <v-switch v-model="settings.integrations.github.enabled"
                        label="Enable GitHub Integration" color="primary" density="compact" />
              <v-text-field v-if="settings.integrations.github.enabled"
                            v-model="settings.integrations.github.org_name"
                            label="GitHub Organization" variant="outlined" density="compact" />
            </div>
            <div class="mb-4">
              <h3 class="text-base font-medium mb-2">Google Workspace</h3>
              <v-switch v-model="settings.integrations.google_workspace.enabled"
                        label="Enable Google Workspace" color="primary" density="compact" />
              <v-text-field v-if="settings.integrations.google_workspace.enabled"
                            v-model="settings.integrations.google_workspace.domain"
                            label="Domain" variant="outlined" density="compact" />
            </div>
            <v-btn color="primary" variant="flat" @click="saveSettings" :loading="saving">
              Save
            </v-btn>
          </v-tabs-window-item>

          <!-- Agent Limits -->
          <v-tabs-window-item value="agents">
            <v-text-field
              v-model.number="settings.agent_limits.max_concurrent_sub_agents"
              label="Max Concurrent Sub-Agents (empty = unlimited)" type="number"
              variant="outlined" density="compact" class="mb-3" />
            <v-text-field
              v-model.number="settings.agent_limits.sub_agent_default_timeout_minutes"
              label="Default Timeout (minutes)" type="number"
              variant="outlined" density="compact" class="mb-3" />
            <v-combobox
              v-model="settings.agent_limits.allowed_models"
              label="Allowed Models (empty = all)" variant="outlined"
              density="compact" multiple chips class="mb-3" />
            <v-btn color="primary" variant="flat" @click="saveSettings" :loading="saving">
              Save
            </v-btn>
          </v-tabs-window-item>

          <!-- Danger Zone -->
          <v-tabs-window-item value="danger">
            <v-alert type="error" variant="tonal" class="mb-4">
              Deleting an organization is irreversible after the grace period.
            </v-alert>
            <v-text-field
              v-model.number="settings.deletion_grace_period_days"
              label="Deletion Grace Period (days)" type="number"
              variant="outlined" density="compact" class="mb-3"
              hint="7–90 days" />
            <v-btn color="primary" variant="flat" @click="saveSettings" :loading="saving"
                   class="mb-6">
              Update Grace Period
            </v-btn>
            <v-divider class="mb-4" />
            <v-btn color="error" variant="flat" @click="confirmDelete = true">
              Delete Organization
            </v-btn>

            <v-dialog v-model="confirmDelete" max-width="400">
              <v-card>
                <v-card-title>Delete {{ orgStore.activeOrg?.name }}?</v-card-title>
                <v-card-text>
                  This will start a {{ settings.deletion_grace_period_days }}-day grace period.
                  You can cancel the deletion during this time.
                </v-card-text>
                <v-card-actions>
                  <v-spacer />
                  <v-btn @click="confirmDelete = false">Cancel</v-btn>
                  <v-btn color="error" variant="flat" @click="handleDelete">
                    Delete
                  </v-btn>
                </v-card-actions>
              </v-card>
            </v-dialog>
          </v-tabs-window-item>
        </v-tabs-window>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useOrgStore } from '../stores/orgs'

const router = useRouter()
const orgStore = useOrgStore()

const tab = ref('general')
const saving = ref(false)
const confirmDelete = ref(false)

const form = reactive({ name: '' })
const settings = reactive({
  authentication: {
    allowed_oidc_providers: [] as string[],
    api_key_rotation_reminder_days: 90,
  },
  task_defaults: {
    default_required_evidence_types: [] as string[],
    default_priority: 'medium',
  },
  integrations: {
    github: { enabled: false, org_name: null as string | null },
    google_workspace: { enabled: false, domain: null as string | null },
  },
  agent_limits: {
    max_concurrent_sub_agents: null as number | null,
    allowed_models: [] as string[],
    sub_agent_default_timeout_minutes: 30,
  },
  deletion_grace_period_days: 30,
})

watch(() => orgStore.activeOrg, (org) => {
  if (!org) return
  form.name = org.name
  const s = org.settings
  settings.authentication = { ...s.authentication }
  settings.task_defaults = { ...s.task_defaults }
  settings.integrations = {
    github: { ...s.integrations.github },
    google_workspace: { ...s.integrations.google_workspace },
  }
  settings.agent_limits = { ...s.agent_limits }
  settings.deletion_grace_period_days = s.deletion_grace_period_days
}, { immediate: true })

async function saveName() {
  saving.value = true
  try {
    await orgStore.updateName(form.name)
  } finally {
    saving.value = false
  }
}

async function saveSettings() {
  saving.value = true
  try {
    await orgStore.updateSettings({
      authentication: settings.authentication,
      task_defaults: settings.task_defaults,
      integrations: settings.integrations,
      agent_limits: settings.agent_limits,
      deletion_grace_period_days: settings.deletion_grace_period_days,
    })
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  confirmDelete.value = false
  await orgStore.beginDeletion()
  router.push('/orgs')
}
</script>
