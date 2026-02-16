<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-xl font-semibold">Projects</h2>
      <v-btn color="primary" variant="flat" size="small" @click="showCreate = true">
        <v-icon start>mdi-plus</v-icon>
        New Project
      </v-btn>
    </div>

    <!-- Loading -->
    <div v-if="projectStore.loading" class="flex items-center justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Kanban Board -->
    <div v-else class="kanban-board">
      <div
        v-for="stage in STAGES"
        :key="stage"
        class="kanban-column"
        @dragover.prevent="onDragOver($event, stage)"
        @dragleave="onDragLeave($event)"
        @drop="onDrop($event, stage)"
      >
        <!-- Column header -->
        <div class="column-header">
          <div class="flex items-center gap-2">
            <span class="stage-dot" :style="{ background: STAGE_COLORS[stage] }" />
            <span class="font-medium text-sm">{{ STAGE_LABELS[stage] }}</span>
          </div>
          <span class="text-xs px-1.5 py-0.5 rounded-full" style="background: var(--surface-secondary); color: var(--text-tertiary);">
            {{ projectStore.projectsByStage[stage]?.length ?? 0 }}
          </span>
        </div>

        <!-- Cards -->
        <div class="column-body">
          <TransitionGroup name="card">
            <ProjectCard
              v-for="project in projectStore.projectsByStage[stage]"
              :key="project.id"
              :project="project"
              @click="selectedProject = project"
            />
          </TransitionGroup>

          <!-- Empty state -->
          <div v-if="!projectStore.projectsByStage[stage]?.length" class="empty-column">
            Drop projects here
          </div>
        </div>
      </div>
    </div>

    <!-- Drag rejection tooltip -->
    <v-snackbar v-model="showError" :timeout="3000" color="error" location="top">
      {{ errorMessage }}
    </v-snackbar>

    <!-- Create Dialog -->
    <CreateProjectDialog v-model="showCreate" @created="handleCreate" />

    <!-- Detail Panel -->
    <ProjectDetailPanel :project="selectedProject" @close="selectedProject = null" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore, STAGES, STAGE_LABELS, STAGE_COLORS, type Stage } from '../stores/projects'
import { useSSE } from '../composables/useSSE'
import ProjectCard from '../components/ProjectCard.vue'
import CreateProjectDialog from '../components/CreateProjectDialog.vue'
import ProjectDetailPanel from '../components/ProjectDetailPanel.vue'
import type { Project } from '../api/projects'

const route = useRoute()
const orgSlug = computed(() => route.params.orgSlug as string)
const projectStore = useProjectStore()
const { connect, disconnect } = useSSE()

const showCreate = ref(false)
const selectedProject = ref<Project | null>(null)
const showError = ref(false)
const errorMessage = ref('')

// Drag-and-drop validation
const STAGE_INDEX: Record<string, number> = Object.fromEntries(STAGES.map((s, i) => [s, i]))

function isValidDrop(fromStage: string, toStage: string): { valid: boolean; reason: string } {
  if (fromStage === toStage) return { valid: false, reason: 'Already in this stage' }
  const fromIdx = STAGE_INDEX[fromStage]
  const toIdx = STAGE_INDEX[toStage]
  if (toIdx < fromIdx) return { valid: true, reason: '' } // backward always ok
  if (toIdx === fromIdx + 1) return { valid: true, reason: '' } // forward one step
  return { valid: false, reason: `Cannot skip stages. Next: ${STAGE_LABELS[STAGES[fromIdx + 1]]}` }
}

function onDragOver(e: DragEvent, stage: Stage) {
  const el = (e.currentTarget as HTMLElement)
  el.classList.add('drag-over')
}

function onDragLeave(e: DragEvent) {
  const el = (e.currentTarget as HTMLElement)
  el.classList.remove('drag-over')
}

async function onDrop(e: DragEvent, toStage: Stage) {
  const el = (e.currentTarget as HTMLElement)
  el.classList.remove('drag-over')

  const projectId = e.dataTransfer?.getData('application/x-project-id')
  const fromStage = e.dataTransfer?.getData('application/x-project-stage')
  if (!projectId || !fromStage) return

  const check = isValidDrop(fromStage, toStage)
  if (!check.valid) {
    errorMessage.value = check.reason
    showError.value = true
    return
  }

  try {
    await projectStore.transition(orgSlug.value, projectId, toStage)
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail ?? 'Transition failed'
    showError.value = true
  }
}

async function handleCreate(body: { name: string; type: string; description?: string }) {
  try {
    await projectStore.create(orgSlug.value, body)
    showCreate.value = false
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail ?? 'Failed to create project'
    showError.value = true
  }
}

onMounted(() => {
  projectStore.fetchProjects(orgSlug.value)
  connect(orgSlug.value)
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
  min-width: 220px;
  width: 220px;
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

.stage-dot {
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

/* Card transition animations */
.card-move,
.card-enter-active,
.card-leave-active {
  transition: all 0.3s ease;
}
.card-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}
.card-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
.card-leave-active {
  position: absolute;
}
</style>
