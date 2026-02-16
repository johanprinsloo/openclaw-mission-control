<template>
  <v-navigation-drawer
    :model-value="!!task"
    @update:model-value="!$event && $emit('close')"
    location="right"
    temporary
    width="480"
  >
    <template v-if="task">
      <div class="pa-4">
        <!-- Header -->
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold">{{ task.title }}</h3>
          <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('close')" />
        </div>

        <!-- Status & Priority -->
        <div class="flex gap-2 mb-4">
          <v-chip :color="STATUS_COLORS[task.status as Status]" size="small" variant="flat">
            {{ STATUS_LABELS[task.status as Status] || task.status }}
          </v-chip>
          <v-chip :color="PRIORITY_COLORS[task.priority]" size="small" variant="flat">
            {{ PRIORITY_LABELS[task.priority] || task.priority }}
          </v-chip>
          <v-chip size="small" variant="outlined">{{ task.type }}</v-chip>
        </div>

        <!-- Description -->
        <div v-if="task.description" class="mb-4">
          <h4 class="text-sm font-medium mb-1" style="color: var(--text-secondary);">Description</h4>
          <p class="text-sm">{{ task.description }}</p>
        </div>

        <!-- Projects -->
        <div class="mb-4">
          <h4 class="text-sm font-medium mb-1" style="color: var(--text-secondary);">Projects</h4>
          <div class="flex flex-wrap gap-1">
            <v-chip v-for="p in taskProjects" :key="p.id" size="small" variant="outlined">{{ p.name }}</v-chip>
            <span v-if="!taskProjects.length" class="text-sm" style="color: var(--text-tertiary);">None</span>
          </div>
        </div>

        <!-- Assignees -->
        <div class="mb-4">
          <h4 class="text-sm font-medium mb-1" style="color: var(--text-secondary);">Assignees</h4>
          <div class="flex flex-wrap gap-1">
            <v-chip v-for="u in taskAssignees" :key="u.id" size="small" variant="outlined">
              {{ u.display_name || u.email }}
            </v-chip>
            <span v-if="!taskAssignees.length" class="text-sm" style="color: var(--text-tertiary);">Unassigned</span>
          </div>
        </div>

        <!-- Dependencies -->
        <div class="mb-4">
          <h4 class="text-sm font-medium mb-2" style="color: var(--text-secondary);">
            Dependencies
            <v-btn icon="mdi-plus" variant="text" size="x-small" @click="showAddDep = true" />
          </h4>
          <div v-if="task.dependency_ids.length" class="flex flex-col gap-1">
            <div v-for="depId in task.dependency_ids" :key="depId" class="flex items-center gap-2">
              <v-icon size="14" color="warning">mdi-link-variant</v-icon>
              <span class="text-sm">{{ depTaskTitle(depId) }}</span>
              <v-btn icon="mdi-close" variant="text" size="x-small" @click="removeDep(depId)" />
            </div>
          </div>
          <span v-else class="text-sm" style="color: var(--text-tertiary);">No dependencies</span>
        </div>

        <!-- Evidence -->
        <div class="mb-4">
          <h4 class="text-sm font-medium mb-1" style="color: var(--text-secondary);">Evidence</h4>
          <div v-if="task.required_evidence_types.length" class="text-xs mb-2" style="color: var(--text-tertiary);">
            Required: {{ task.required_evidence_types.join(', ') }}
          </div>
          <div v-if="task.evidence.length" class="flex flex-col gap-1">
            <div v-for="ev in task.evidence" :key="ev.id" class="flex items-center gap-2 text-sm">
              <v-icon size="14" color="success">mdi-check-circle</v-icon>
              <span class="font-medium">{{ ev.type }}</span>
              <a :href="ev.url" target="_blank" class="text-blue-500 truncate">{{ ev.url }}</a>
            </div>
          </div>
          <span v-else class="text-sm" style="color: var(--text-tertiary);">No evidence submitted</span>
        </div>

        <!-- Timestamps -->
        <div class="text-xs" style="color: var(--text-tertiary);">
          <div>Created: {{ new Date(task.created_at).toLocaleString() }}</div>
          <div>Updated: {{ new Date(task.updated_at).toLocaleString() }}</div>
          <div v-if="task.completed_at">Completed: {{ new Date(task.completed_at).toLocaleString() }}</div>
        </div>
      </div>

      <!-- Add dependency dialog -->
      <v-dialog v-model="showAddDep" max-width="400">
        <v-card>
          <v-card-title class="text-sm">Add Dependency</v-card-title>
          <v-card-text>
            <v-select
              v-model="depTarget"
              :items="availableDepTargets"
              item-title="title"
              item-value="id"
              label="Blocked by..."
              variant="outlined"
              density="compact"
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="showAddDep = false">Cancel</v-btn>
            <v-btn color="primary" variant="flat" :disabled="!depTarget" @click="addDep">Add</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </template>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useTaskStore, STATUS_LABELS, STATUS_COLORS, PRIORITY_COLORS, PRIORITY_LABELS, type Status } from '../stores/tasks'
import { addDependency, removeDependency, type Task } from '../api/tasks'
import type { Project } from '../api/projects'

interface User {
  id: string
  display_name?: string
  email: string
}

const props = defineProps<{
  task: Task | null
  projects: Project[]
  users: User[]
}>()

const emit = defineEmits<{ close: []; updated: [] }>()

const route = useRoute()
const orgSlug = computed(() => route.params.orgSlug as string)
const taskStore = useTaskStore()
const showAddDep = ref(false)
const depTarget = ref<string | null>(null)

const taskProjects = computed(() =>
  props.task ? props.projects.filter(p => props.task!.project_ids.includes(p.id)) : []
)

const taskAssignees = computed(() =>
  props.task ? props.users.filter(u => props.task!.assignee_ids.includes(u.id)) : []
)

const availableDepTargets = computed(() =>
  taskStore.tasks
    .filter(t => t.id !== props.task?.id && !props.task?.dependency_ids.includes(t.id))
    .map(t => ({ id: t.id, title: t.title }))
)

function depTaskTitle(depId: string): string {
  return taskStore.tasks.find(t => t.id === depId)?.title || depId.slice(0, 8)
}

async function addDep() {
  if (!props.task || !depTarget.value) return
  try {
    await addDependency(orgSlug.value, props.task.id, depTarget.value)
    showAddDep.value = false
    depTarget.value = null
    emit('updated')
  } catch { /* handled by parent */ }
}

async function removeDep(blockedById: string) {
  if (!props.task) return
  try {
    await removeDependency(orgSlug.value, props.task.id, blockedById)
    emit('updated')
  } catch { /* handled by parent */ }
}
</script>
