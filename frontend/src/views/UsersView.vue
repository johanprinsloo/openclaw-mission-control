<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-xl font-semibold">Users</h2>
      <v-btn color="primary" variant="flat" size="small" @click="showInviteDialog = true">
        <v-icon start>mdi-account-plus</v-icon>
        Invite User
      </v-btn>
    </div>

    <!-- AG Grid Table -->
    <div class="flex-1 ag-theme-alpine" style="min-height: 300px;">
      <ag-grid-vue
        class="w-full h-full"
        :columnDefs="columnDefs"
        :rowData="users"
        :defaultColDef="defaultColDef"
        :animateRows="true"
        :suppressCellFocus="true"
        rowSelection="single"
        @grid-ready="onGridReady"
      />
    </div>

    <!-- Invite User Dialog -->
    <v-dialog v-model="showInviteDialog" max-width="500">
      <v-card>
        <v-card-title>Invite User</v-card-title>
        <v-card-text>
          <v-btn-toggle v-model="inviteForm.type" mandatory color="primary" class="mb-4">
            <v-btn value="human" size="small">Human</v-btn>
            <v-btn value="agent" size="small">Agent</v-btn>
          </v-btn-toggle>

          <v-text-field
            v-if="inviteForm.type === 'human'"
            v-model="inviteForm.email"
            label="Email"
            variant="outlined"
            density="compact"
            class="mb-3"
            type="email"
          />
          <v-text-field
            v-if="inviteForm.type === 'agent'"
            v-model="inviteForm.identifier"
            label="Agent Identifier"
            variant="outlined"
            density="compact"
            class="mb-3"
            hint="e.g. deploy-bot, ci-runner"
          />
          <v-text-field
            v-model="inviteForm.display_name"
            label="Display Name"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-select
            v-model="inviteForm.role"
            :items="[{ title: 'Contributor', value: 'contributor' }, { title: 'Administrator', value: 'administrator' }]"
            label="Role"
            variant="outlined"
            density="compact"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="showInviteDialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" @click="handleInvite" :loading="inviting">
            Add User
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- API Key Display Dialog (one-time) -->
    <v-dialog v-model="showApiKeyDialog" max-width="550" persistent>
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon color="warning" class="mr-2">mdi-key-alert</v-icon>
          API Key Created
        </v-card-title>
        <v-card-text>
          <v-alert type="warning" variant="tonal" class="mb-4" density="compact">
            This key will only be shown once. Copy it now.
          </v-alert>
          <div class="d-flex align-center gap-2 pa-3 rounded"
               style="background: var(--surface-secondary); font-family: monospace; font-size: 0.8rem; word-break: break-all;">
            <span class="flex-1">{{ displayedApiKey }}</span>
            <v-btn icon size="small" variant="text" @click="copyKey">
              <v-icon>{{ copied ? 'mdi-check' : 'mdi-content-copy' }}</v-icon>
            </v-btn>
          </div>
          <div v-if="apiKeyExpiresAt" class="mt-2 text-caption" style="color: var(--text-tertiary);">
            Previous key valid until: {{ new Date(apiKeyExpiresAt).toLocaleString() }}
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" variant="flat" @click="closeApiKeyDialog">
            I've copied the key
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Rotate Key Confirmation Dialog -->
    <v-dialog v-model="showRotateDialog" max-width="450">
      <v-card>
        <v-card-title>Rotate API Key</v-card-title>
        <v-card-text>
          <p>This will generate a new API key for <strong>{{ rotateTarget?.display_name }}</strong>.</p>
          <p class="mt-2">The current key will remain valid for <strong>24 hours</strong> (grace period).</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="showRotateDialog = false">Cancel</v-btn>
          <v-btn color="warning" variant="flat" @click="handleRotate" :loading="rotating">
            Rotate Key
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Remove User Confirmation -->
    <v-dialog v-model="showRemoveDialog" max-width="400">
      <v-card>
        <v-card-title>Remove User</v-card-title>
        <v-card-text>
          Remove <strong>{{ removeTarget?.display_name }}</strong> from this organization?
          This will immediately revoke their access.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="showRemoveDialog = false">Cancel</v-btn>
          <v-btn color="error" variant="flat" @click="handleRemove" :loading="removing">
            Remove
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, h, defineComponent } from 'vue'
import { useRoute } from 'vue-router'
import { AgGridVue } from 'ag-grid-vue3'
import { AllCommunityModule, ModuleRegistry, type ColDef, type GridApi } from 'ag-grid-community'
import {
  listUsers,
  addUser,
  removeUser,
  rotateApiKey,
  type UserInfo,
  type UserAddPayload,
} from '../api/users'

ModuleRegistry.registerModules([AllCommunityModule])

const route = useRoute()
const orgSlug = () => route.params.orgSlug as string

// State
const users = ref<UserInfo[]>([])
const gridApi = ref<GridApi | null>(null)
const loading = ref(false)

// Invite dialog
const showInviteDialog = ref(false)
const inviting = ref(false)
const inviteForm = reactive<UserAddPayload>({
  type: 'human',
  email: '',
  identifier: '',
  display_name: '',
  role: 'contributor',
})

// API key display dialog
const showApiKeyDialog = ref(false)
const displayedApiKey = ref('')
const apiKeyExpiresAt = ref<string | null>(null)
const copied = ref(false)

// Rotate dialog
const showRotateDialog = ref(false)
const rotating = ref(false)
const rotateTarget = ref<UserInfo | null>(null)

// Remove dialog
const showRemoveDialog = ref(false)
const removing = ref(false)
const removeTarget = ref<UserInfo | null>(null)

// AG Grid config
const defaultColDef: ColDef = {
  sortable: true,
  resizable: true,
  suppressHeaderMenuButton: true,
}

// Actions cell renderer as a Vue component
const ActionsCellRenderer = defineComponent({
  props: ['params'],
  setup(props) {
    return () => {
      const user = props.params.data as UserInfo
      const buttons = []

      if (user.type === 'agent' && user.has_api_key) {
        buttons.push(
          h('button', {
            class: 'action-btn',
            title: 'Rotate API Key',
            onClick: () => openRotateDialog(user),
          }, '🔄')
        )
      }

      buttons.push(
        h('button', {
          class: 'action-btn action-btn-danger',
          title: 'Remove User',
          onClick: () => openRemoveDialog(user),
        }, '✕')
      )

      return h('div', { class: 'actions-cell' }, buttons)
    }
  },
})

const columnDefs: ColDef[] = [
  {
    headerName: 'Name',
    field: 'display_name',
    flex: 2,
    minWidth: 150,
  },
  {
    headerName: 'Type',
    field: 'type',
    width: 100,
    cellRenderer: (params: any) => {
      const type = params.value
      const icon = type === 'agent' ? '🤖' : '👤'
      return `${icon} ${type.charAt(0).toUpperCase() + type.slice(1)}`
    },
  },
  {
    headerName: 'Role',
    field: 'role',
    width: 130,
    cellRenderer: (params: any) => {
      const role = params.value
      return role === 'administrator' ? '🛡️ Admin' : '✏️ Contributor'
    },
  },
  {
    headerName: 'Last Active',
    field: 'last_active',
    width: 150,
    cellRenderer: (params: any) => {
      return params.value ? new Date(params.value).toLocaleDateString() : '—'
    },
  },
  {
    headerName: 'Actions',
    width: 100,
    sortable: false,
    resizable: false,
    cellRenderer: ActionsCellRenderer,
  },
]

// Handlers
function onGridReady(params: any) {
  gridApi.value = params.api
}

async function fetchUsers() {
  loading.value = true
  try {
    users.value = await listUsers(orgSlug())
  } finally {
    loading.value = false
  }
}

async function handleInvite() {
  inviting.value = true
  try {
    const payload: UserAddPayload = {
      type: inviteForm.type,
      display_name: inviteForm.display_name,
      role: inviteForm.role,
    }
    if (inviteForm.type === 'human') {
      payload.email = inviteForm.email
    } else {
      payload.identifier = inviteForm.identifier
    }
    const result = await addUser(orgSlug(), payload)
    showInviteDialog.value = false

    if (result.api_key) {
      displayedApiKey.value = result.api_key
      apiKeyExpiresAt.value = null
      showApiKeyDialog.value = true
    }

    // Reset form
    inviteForm.type = 'human'
    inviteForm.email = ''
    inviteForm.identifier = ''
    inviteForm.display_name = ''
    inviteForm.role = 'contributor'

    await fetchUsers()
  } finally {
    inviting.value = false
  }
}

function openRotateDialog(user: UserInfo) {
  rotateTarget.value = user
  showRotateDialog.value = true
}

async function handleRotate() {
  if (!rotateTarget.value) return
  rotating.value = true
  try {
    const result = await rotateApiKey(orgSlug(), rotateTarget.value.id)
    showRotateDialog.value = false
    displayedApiKey.value = result.api_key
    apiKeyExpiresAt.value = result.previous_key_expires_at
    showApiKeyDialog.value = true
  } finally {
    rotating.value = false
  }
}

function openRemoveDialog(user: UserInfo) {
  removeTarget.value = user
  showRemoveDialog.value = true
}

async function handleRemove() {
  if (!removeTarget.value) return
  removing.value = true
  try {
    await removeUser(orgSlug(), removeTarget.value.id)
    showRemoveDialog.value = false
    await fetchUsers()
  } finally {
    removing.value = false
  }
}

async function copyKey() {
  await navigator.clipboard.writeText(displayedApiKey.value)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

function closeApiKeyDialog() {
  showApiKeyDialog.value = false
  displayedApiKey.value = ''
  apiKeyExpiresAt.value = null
}

onMounted(fetchUsers)
</script>

<style scoped>
.ag-theme-alpine {
  --ag-header-height: 36px;
  --ag-row-height: 40px;
  --ag-font-size: 13px;
}

:deep(.actions-cell) {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 100%;
}

:deep(.action-btn) {
  cursor: pointer;
  background: none;
  border: none;
  font-size: 14px;
  padding: 2px 4px;
  border-radius: 4px;
  opacity: 0.7;
  transition: opacity 0.15s;
}

:deep(.action-btn:hover) {
  opacity: 1;
}

:deep(.action-btn-danger:hover) {
  color: #ef4444;
}
</style>
