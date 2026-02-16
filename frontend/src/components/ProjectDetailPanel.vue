<template>
  <v-navigation-drawer
    :model-value="!!project"
    @update:model-value="$emit('close')"
    location="right"
    temporary
    width="420"
  >
    <template v-if="project">
      <div class="pa-4">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold">{{ project.name }}</h3>
          <v-btn icon size="small" variant="text" @click="$emit('close')">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </div>

        <!-- Stage badge -->
        <div class="mb-4">
          <span class="stage-badge" :style="{ background: stageColor, color: '#fff' }">
            {{ stageLabel }}
          </span>
          <span class="type-badge ml-2">{{ project.type }}</span>
        </div>

        <!-- Description -->
        <div v-if="project.description" class="mb-4">
          <div class="text-xs font-semibold uppercase mb-1" style="color: var(--text-tertiary);">Description</div>
          <p class="text-sm" style="color: var(--text-secondary);">{{ project.description }}</p>
        </div>

        <!-- Metadata -->
        <div class="mb-4">
          <div class="text-xs font-semibold uppercase mb-2" style="color: var(--text-tertiary);">Details</div>
          <div class="grid grid-cols-2 gap-2 text-sm">
            <div style="color: var(--text-tertiary);">Owner</div>
            <div>{{ project.owner_id?.slice(0, 8) ?? '—' }}</div>
            <div style="color: var(--text-tertiary);">Created</div>
            <div>{{ new Date(project.created_at).toLocaleDateString() }}</div>
            <div style="color: var(--text-tertiary);">Updated</div>
            <div>{{ new Date(project.updated_at).toLocaleDateString() }}</div>
          </div>
        </div>

        <!-- Task summary -->
        <div class="mb-4">
          <div class="text-xs font-semibold uppercase mb-2" style="color: var(--text-tertiary);">Tasks</div>
          <div class="flex items-center gap-3">
            <div class="text-2xl font-bold" style="color: var(--action-primary);">
              {{ project.task_complete_count }}<span class="text-sm font-normal" style="color: var(--text-tertiary);">/{{ project.task_count }}</span>
            </div>
            <div class="text-sm" style="color: var(--text-secondary);">complete</div>
          </div>
          <div v-if="project.task_count > 0" class="mt-2 h-2 rounded-full overflow-hidden" style="background: var(--border-subtle);">
            <div class="h-full rounded-full" :style="{ width: progressPercent + '%', background: 'var(--action-primary)' }" />
          </div>
        </div>

        <!-- Links -->
        <div v-if="project.links && Object.keys(project.links).length > 0" class="mb-4">
          <div class="text-xs font-semibold uppercase mb-2" style="color: var(--text-tertiary);">Links</div>
          <div v-for="(url, label) in project.links" :key="label" class="mb-1">
            <a :href="url" target="_blank" class="text-sm" style="color: var(--action-primary);">
              {{ label }}
            </a>
          </div>
        </div>
      </div>
    </template>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Project } from '../api/projects'
import { STAGE_LABELS, STAGE_COLORS, type Stage } from '../stores/projects'

const props = defineProps<{ project: Project | null }>()
defineEmits<{ close: [] }>()

const stageLabel = computed(() => STAGE_LABELS[(props.project?.stage ?? 'definition') as Stage])
const stageColor = computed(() => STAGE_COLORS[(props.project?.stage ?? 'definition') as Stage])
const progressPercent = computed(() =>
  props.project && props.project.task_count > 0
    ? Math.round((props.project.task_complete_count / props.project.task_count) * 100)
    : 0
)
</script>

<style scoped>
.stage-badge {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 3px 8px;
  border-radius: 4px;
}
.type-badge {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--surface-secondary);
  color: var(--text-secondary);
}
</style>
