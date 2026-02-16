<template>
  <div
    class="project-card"
    :style="{ borderLeftColor: stageColor }"
    draggable="true"
    @dragstart="onDragStart"
    @click="$emit('click', project)"
  >
    <div class="flex items-center justify-between mb-1">
      <span class="font-medium text-sm truncate" style="color: var(--text-primary);">
        {{ project.name }}
      </span>
      <span class="type-badge" :class="`type-${project.type}`">
        {{ project.type }}
      </span>
    </div>

    <div class="text-xs mb-2" style="color: var(--text-tertiary);">
      {{ ownerLabel }}
    </div>

    <!-- Task progress bar -->
    <div v-if="project.task_count > 0" class="progress-container">
      <div class="progress-bar" :style="{ width: progressPercent + '%' }" />
      <span class="progress-label">{{ project.task_complete_count }}/{{ project.task_count }}</span>
    </div>
    <div v-else class="text-xs" style="color: var(--text-tertiary);">No tasks</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Project } from '../api/projects'
import { STAGE_COLORS, type Stage } from '../stores/projects'

const props = defineProps<{ project: Project }>()
defineEmits<{ click: [project: Project] }>()

const stageColor = computed(() => STAGE_COLORS[props.project.stage as Stage] || '#6B7280')
const ownerLabel = computed(() => props.project.owner_id ? `Owner: ${props.project.owner_id.slice(0, 8)}…` : 'No owner')
const progressPercent = computed(() =>
  props.project.task_count > 0
    ? Math.round((props.project.task_complete_count / props.project.task_count) * 100)
    : 0
)

function onDragStart(e: DragEvent) {
  e.dataTransfer?.setData('application/x-project-id', props.project.id)
  e.dataTransfer?.setData('application/x-project-stage', props.project.stage)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}
</script>

<style scoped>
.project-card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-subtle);
  border-left: 4px solid;
  border-radius: 8px;
  padding: 12px;
  cursor: grab;
  transition: box-shadow 0.15s, transform 0.15s;
  user-select: none;
}
.project-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  transform: translateY(-1px);
}
.project-card:active {
  cursor: grabbing;
  opacity: 0.7;
}

.type-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--surface-secondary);
  color: var(--text-secondary);
}
.type-software { color: #3B82F6; background: #EFF6FF; }
.type-docs { color: #8B5CF6; background: #F5F3FF; }
.type-launch { color: #EF4444; background: #FEF2F2; }

.progress-container {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 14px;
}
.progress-bar {
  flex: 1;
  height: 4px;
  background: var(--action-primary);
  border-radius: 2px;
  transition: width 0.3s ease;
}
.progress-container::before {
  content: '';
  position: absolute;
  left: 0;
  width: 100%;
  height: 4px;
  background: var(--border-subtle);
  border-radius: 2px;
}
.progress-container {
  position: relative;
}
.progress-bar {
  position: relative;
  z-index: 1;
}
.progress-label {
  font-size: 10px;
  color: var(--text-tertiary);
  white-space: nowrap;
  position: relative;
  z-index: 1;
}
</style>
