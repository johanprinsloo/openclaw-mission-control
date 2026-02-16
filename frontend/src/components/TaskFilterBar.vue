<template>
  <div class="flex flex-wrap items-center gap-3">
    <v-select
      v-model="selectedProjects"
      :items="projectItems"
      item-title="name"
      item-value="id"
      label="Project"
      multiple
      density="compact"
      variant="outlined"
      hide-details
      clearable
      class="filter-select"
      @update:model-value="emitFilters"
    />
    <v-select
      v-model="selectedAssignees"
      :items="userItems"
      item-title="label"
      item-value="id"
      label="Assignee"
      multiple
      density="compact"
      variant="outlined"
      hide-details
      clearable
      class="filter-select"
      @update:model-value="emitFilters"
    />
    <v-select
      v-model="selectedPriority"
      :items="priorityItems"
      label="Priority"
      density="compact"
      variant="outlined"
      hide-details
      clearable
      class="filter-select"
      @update:model-value="emitFilters"
    />
    <v-checkbox
      v-model="myTasks"
      label="My Tasks"
      density="compact"
      hide-details
      class="shrink"
      @update:model-value="emitFilters"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Project } from '../api/projects'

interface User {
  id: string
  display_name?: string
  email: string
}

const props = defineProps<{
  projects: Project[]
  users: User[]
}>()

const emit = defineEmits<{
  'update:filters': [filters: any]
}>()

const selectedProjects = ref<string[]>([])
const selectedAssignees = ref<string[]>([])
const selectedPriority = ref<string | null>(null)
const myTasks = ref(false)

const projectItems = computed(() => props.projects.map(p => ({ id: p.id, name: p.name })))
const userItems = computed(() => props.users.map(u => ({ id: u.id, label: u.display_name || u.email })))
const priorityItems = [
  { title: 'Critical', value: 'critical' },
  { title: 'High', value: 'high' },
  { title: 'Medium', value: 'medium' },
  { title: 'Low', value: 'low' },
]

function emitFilters() {
  emit('update:filters', {
    project_id: selectedProjects.value.length === 1 ? selectedProjects.value[0] : undefined,
    assignee_id: selectedAssignees.value.length === 1 ? selectedAssignees.value[0] : undefined,
    priority: selectedPriority.value || undefined,
  })
}
</script>

<style scoped>
.filter-select {
  max-width: 200px;
  min-width: 160px;
}
</style>
