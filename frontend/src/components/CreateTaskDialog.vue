<template>
  <v-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" max-width="560" persistent>
    <v-card>
      <v-card-title class="text-lg font-semibold">New Task</v-card-title>
      <v-card-text>
        <v-text-field v-model="form.title" label="Title" variant="outlined" density="compact" class="mb-3" :rules="[v => !!v || 'Required']" />
        <v-textarea v-model="form.description" label="Description" variant="outlined" density="compact" rows="3" class="mb-3" />

        <div class="grid grid-cols-2 gap-3 mb-3">
          <v-select v-model="form.type" :items="typeItems" label="Type" variant="outlined" density="compact" hide-details />
          <v-select v-model="form.priority" :items="priorityItems" label="Priority" variant="outlined" density="compact" hide-details />
        </div>

        <v-select
          v-model="form.project_ids"
          :items="projectItems"
          item-title="name"
          item-value="id"
          label="Projects"
          multiple
          variant="outlined"
          density="compact"
          hide-details
          class="mb-3"
        />

        <v-select
          v-model="form.assignee_ids"
          :items="userItems"
          item-title="label"
          item-value="id"
          label="Assignees"
          multiple
          variant="outlined"
          density="compact"
          hide-details
          class="mb-3"
        />

        <v-select
          v-model="form.required_evidence_types"
          :items="evidenceItems"
          label="Required Evidence"
          multiple
          variant="outlined"
          density="compact"
          hide-details
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :disabled="!form.title" @click="submit">Create</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { Project } from '../api/projects'

interface User {
  id: string
  display_name?: string
  email: string
}

const props = defineProps<{
  modelValue: boolean
  projects: Project[]
  users: User[]
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  created: [body: any]
}>()

const form = ref({
  title: '',
  description: '',
  type: 'chore',
  priority: 'medium',
  project_ids: [] as string[],
  assignee_ids: [] as string[],
  required_evidence_types: [] as string[],
})

const typeItems = [
  { title: 'Bug', value: 'bug' },
  { title: 'Feature', value: 'feature' },
  { title: 'Chore', value: 'chore' },
]
const priorityItems = [
  { title: 'Critical', value: 'critical' },
  { title: 'High', value: 'high' },
  { title: 'Medium', value: 'medium' },
  { title: 'Low', value: 'low' },
]
const evidenceItems = [
  { title: 'PR Link', value: 'pr_link' },
  { title: 'Test Results', value: 'test_results' },
  { title: 'Doc URL', value: 'doc_url' },
]

const projectItems = computed(() => props.projects.map(p => ({ id: p.id, name: p.name })))
const userItems = computed(() => props.users.map(u => ({ id: u.id, label: u.display_name || u.email })))

watch(() => props.modelValue, (v) => {
  if (v) {
    form.value = { title: '', description: '', type: 'chore', priority: 'medium', project_ids: [], assignee_ids: [], required_evidence_types: [] }
  }
})

function submit() {
  emit('created', { ...form.value })
}
</script>
