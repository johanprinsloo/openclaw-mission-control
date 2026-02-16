<template>
  <div
    class="task-card"
    draggable="true"
    @dragstart="onDragStart"
    @click="$emit('click')"
  >
    <!-- Priority bar -->
    <div class="priority-bar" :style="{ background: PRIORITY_COLORS[task.priority] || '#6B7280' }" />

    <div class="card-content">
      <!-- Title -->
      <div class="text-sm font-medium leading-tight mb-1">{{ task.title }}</div>

      <!-- Type badge -->
      <div class="flex items-center gap-1 mb-2">
        <span class="type-badge" :class="task.type">{{ task.type }}</span>
        <v-icon v-if="task.dependency_ids.length > 0" size="14" color="warning" title="Has dependencies">
          mdi-link-variant
        </v-icon>
      </div>

      <!-- Project badges -->
      <div v-if="taskProjects.length" class="flex flex-wrap gap-1 mb-2">
        <span
          v-for="p in taskProjects"
          :key="p.id"
          class="project-badge"
        >{{ p.name }}</span>
      </div>

      <!-- Assignees -->
      <div v-if="taskAssignees.length" class="flex items-center gap-1">
        <v-avatar
          v-for="u in taskAssignees"
          :key="u.id"
          size="20"
          :color="stringToColor(u.display_name || u.email)"
          class="text-white"
        >
          <span class="text-xs">{{ initials(u.display_name || u.email) }}</span>
        </v-avatar>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Task } from '../api/tasks'
import type { Project } from '../api/projects'
import { PRIORITY_COLORS } from '../stores/tasks'

interface User {
  id: string
  display_name?: string
  email: string
}

const props = defineProps<{
  task: Task
  projects: Project[]
  users: User[]
}>()

defineEmits<{ click: [] }>()

const taskProjects = computed(() =>
  props.projects.filter(p => props.task.project_ids.includes(p.id))
)

const taskAssignees = computed(() =>
  props.users.filter(u => props.task.assignee_ids.includes(u.id))
)

function onDragStart(e: DragEvent) {
  e.dataTransfer?.setData('application/x-task-id', props.task.id)
  e.dataTransfer?.setData('application/x-task-status', props.task.status)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

function initials(name: string): string {
  return name.split(/[\s@]/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('')
}

function stringToColor(s: string): string {
  let hash = 0
  for (let i = 0; i < s.length; i++) hash = s.charCodeAt(i) + ((hash << 5) - hash)
  const h = hash % 360
  return `hsl(${h}, 55%, 45%)`
}
</script>

<style scoped>
.task-card {
  display: flex;
  background: var(--surface-primary);
  border-radius: 8px;
  cursor: pointer;
  overflow: hidden;
  transition: box-shadow 0.15s, transform 0.15s;
  border: 1px solid var(--border-subtle);
}
.task-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  transform: translateY(-1px);
}
.priority-bar {
  width: 4px;
  flex-shrink: 0;
}
.card-content {
  padding: 10px;
  flex: 1;
  min-width: 0;
}
.type-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.type-badge.bug { background: #FEE2E2; color: #991B1B; }
.type-badge.feature { background: #DBEAFE; color: #1E40AF; }
.type-badge.chore { background: #F3F4F6; color: #374151; }
.project-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--surface-secondary);
  color: var(--text-secondary);
}
</style>
