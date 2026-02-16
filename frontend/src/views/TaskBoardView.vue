<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-3">
        <h2 class="text-xl font-semibold">Tasks</h2>
        <v-btn-toggle v-model="viewMode" mandatory density="compact" variant="outlined" color="primary">
          <v-btn value="board" size="small"><v-icon>mdi-view-column</v-icon></v-btn>
          <v-btn value="table" size="small"><v-icon>mdi-table</v-icon></v-btn>
        </v-btn-toggle>
      </div>
      <v-btn color="primary" variant="flat" size="small" @click="showCreate = true">
        <v-icon start>mdi-plus</v-icon>
        New Task
      </v-btn>
    </div>

    <!-- Filter Bar -->
    <TaskFilterBar
      :projects="projects"
      :users="users"
      @update:filters="onFiltersChanged"
      class="mb-4"
    />

    <!-- Loading -->
    <div v-if="taskStore.loading" class="flex items-center justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Kanban Board -->
    <div v-else-if="viewMode === 'board'" class="kanban-board">
      <div
        v-for="status in STATUSES"
        :key="status"
        class="kanban-column"
        @dragover.prevent="onDragOver($event, status)"
        @dragleave="onDragLeave($event)"
        @drop="onDrop($event, status)"
      >
        <div class="column-header">
          <div class="flex items-center gap-2">
            <span class="status-dot" :style="{ background: STATUS_COLORS[status] }" />
            <span class="font-medium text-sm">{{ STATUS_LABELS[status] }}</span>
          </div>
          <span class="text-xs px-1.5 py-0.5 rounded-full" style="background: var(--surface-secondary); color: var(--text-tertiary);">
            {{ taskStore.tasksByStatus[status]?.length ?? 0 }}
          </span>
        </div>

        <div class="column-body">
          <TransitionGroup name="card">
            <TaskCard
              v-for="task in taskStore.tasksByStatus[status]"
              :key="task.id"
              :task="task"
              :projects="projects"
              :users="users"
              @click="selectedTask = task"
            />
          </TransitionGroup>

          <div v-if="!taskStore.tasksByStatus[status]?.length" class="empty-column">
            Drop tasks here
          </div>
        </div>
      </div>
    </div>

    <!-- AG Grid Table View -->
    <TaskTableView
      v-else
      :tasks="taskStore.tasks"
      :projects="projects"
      :users="users"
      @select="selectedTask = $event"
    />

    <!-- Snackbar -->
    <v-snackbar v-model="showError" :timeout="3000" color="error" location="top">
      {{ errorMessage }}
    </v-snackbar>

    <!-- Create Dialog -->
    <CreateTaskDialog
      v-model="showCreate"
      :projects="projects"
      :users="users"
      @created="handleCreate"
    />

    <!-- Detail Panel -->
    <TaskDetailPanel
      :task="selectedTask"
      :projects="projects"
      :users="users"
      @close="selectedTask = null"
      @updated="handleTaskUpdated"
    />

    <!-- Evidence Modal -->
    <EvidenceModal
      v-model="showEvidence"
      :task="pendingTransitionTask"
      @submit="handleEvidenceSubmit"
      @cancel="cancelTransition"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useTaskStore, STATUSES, STATUS_LABELS, STATUS_COLORS, type Status } from '../stores/tasks'
import { useProjectStore } from '../stores/projects'
import { useSSE } from '../composables/useSSE'
import { listUsers, type UserInfo as User } from '../api/users'
import type { Task, EvidenceSubmission } from '../api/tasks'
import type { Project } from '../api/projects'
import TaskCard from '../components/TaskCard.vue'
import TaskFilterBar from '../components/TaskFilterBar.vue'
import TaskTableView from '../components/TaskTableView.vue'
import CreateTaskDialog from '../components/CreateTaskDialog.vue'
import TaskDetailPanel from '../components/TaskDetailPanel.vue'
import EvidenceModal from '../components/EvidenceModal.vue'

const route = useRoute()
const orgSlug = computed(() => route.params.orgSlug as string)
const taskStore = useTaskStore()
const projectStore = useProjectStore()
const { connect, disconnect } = useSSE()

const viewMode = ref<'board' | 'table'>('board')
const showCreate = ref(false)
const showEvidence = ref(false)
const selectedTask = ref<Task | null>(null)
const showError = ref(false)
const errorMessage = ref('')
const users = ref<User[]>([])
const projects = computed(() => projectStore.projects)

// Pending transition (waiting for evidence)
const pendingTransitionTask = ref<Task | null>(null)
const pendingTransitionStatus = ref<string>('')

// Valid transitions
const VALID_TRANSITIONS: Record<string, string[]> = {
  'backlog': ['in-progress'],
  'in-progress': ['backlog', 'in-review'],
  'in-review': ['in-progress', 'complete'],
  'complete': ['in-review'],
}

function onDragOver(e: DragEvent, _status: Status) {
  (e.currentTarget as HTMLElement).classList.add('drag-over')
}

function onDragLeave(e: DragEvent) {
  (e.currentTarget as HTMLElement).classList.remove('drag-over')
}

async function onDrop(e: DragEvent, toStatus: Status) {
  (e.currentTarget as HTMLElement).classList.remove('drag-over')

  const taskId = e.dataTransfer?.getData('application/x-task-id')
  const fromStatus = e.dataTransfer?.getData('application/x-task-status')
  if (!taskId || !fromStatus || fromStatus === toStatus) return

  const allowed = VALID_TRANSITIONS[fromStatus] || []
  if (!allowed.includes(toStatus)) {
    errorMessage.value = `Cannot transition from ${fromStatus} to ${toStatus}`
    showError.value = true
    return
  }

  const task = taskStore.tasks.find(t => t.id === taskId)
  if (!task) return

  // Check if evidence is needed for completion
  if (toStatus === 'complete' && task.required_evidence_types.length > 0) {
    const submittedTypes = new Set(task.evidence.map(e => e.type))
    const missing = task.required_evidence_types.filter(t => !submittedTypes.has(t))
    if (missing.length > 0) {
      pendingTransitionTask.value = task
      pendingTransitionStatus.value = toStatus
      showEvidence.value = true
      return
    }
  }

  await doTransition(taskId, toStatus)
}

async function doTransition(taskId: string, toStatus: string, evidence: EvidenceSubmission[] = []) {
  try {
    await taskStore.transition(orgSlug.value, taskId, toStatus, evidence)
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail ?? 'Transition failed'
    showError.value = true
  }
}

async function handleEvidenceSubmit(evidence: EvidenceSubmission[]) {
  if (pendingTransitionTask.value) {
    await doTransition(pendingTransitionTask.value.id, pendingTransitionStatus.value, evidence)
  }
  showEvidence.value = false
  pendingTransitionTask.value = null
}

function cancelTransition() {
  showEvidence.value = false
  pendingTransitionTask.value = null
}

async function handleCreate(body: any) {
  try {
    await taskStore.create(orgSlug.value, body)
    showCreate.value = false
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail ?? 'Failed to create task'
    showError.value = true
  }
}

function handleTaskUpdated() {
  taskStore.fetchTasks(orgSlug.value)
}

function onFiltersChanged(f: any) {
  taskStore.setFilters(f)
  taskStore.fetchTasks(orgSlug.value)
}

onMounted(async () => {
  taskStore.fetchTasks(orgSlug.value)
  projectStore.fetchProjects(orgSlug.value)
  connect(orgSlug.value)
  try {
    users.value = await listUsers(orgSlug.value)
  } catch { /* ignore */ }
})

onUnmounted(() => {
  disconnect()
})
</script>

<style scoped>
.kanban-board {
  display: flex;
  gap: 16px;
  flex: 1;
  overflow-x: auto;
  padding-bottom: 8px;
}
.kanban-column {
  min-width: 260px;
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface-secondary);
  border-radius: 10px;
  border: 2px solid transparent;
  transition: border-color 0.15s, background 0.15s;
}
.kanban-column.drag-over {
  border-color: var(--action-primary);
  background: var(--surface-sunken);
}
.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 12px 8px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.column-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.empty-column {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 24px 0;
  border: 2px dashed var(--border-subtle);
  border-radius: 8px;
  min-height: 80px;
}
.card-move, .card-enter-active, .card-leave-active { transition: all 0.3s ease; }
.card-enter-from { opacity: 0; transform: translateY(-10px); }
.card-leave-to { opacity: 0; transform: translateX(20px); }
.card-leave-active { position: absolute; }
</style>
