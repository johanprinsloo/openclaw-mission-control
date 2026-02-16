<template>
  <v-dialog :model-value="modelValue" @update:model-value="!$event && $emit('cancel')" max-width="500" persistent>
    <v-card>
      <v-card-title class="text-lg font-semibold">Submit Evidence</v-card-title>
      <v-card-subtitle v-if="task" class="text-sm">
        Required to complete: <strong>{{ task.title }}</strong>
      </v-card-subtitle>
      <v-card-text>
        <div v-if="task" class="mb-3 text-sm" style="color: var(--text-secondary);">
          Missing evidence types: {{ missingTypes.join(', ') }}
        </div>
        <div v-for="(item, idx) in evidenceItems" :key="idx" class="flex gap-2 mb-3">
          <v-select
            v-model="item.type"
            :items="missingTypeOptions"
            label="Type"
            variant="outlined"
            density="compact"
            hide-details
            style="max-width: 160px;"
          />
          <v-text-field
            v-model="item.url"
            label="URL"
            variant="outlined"
            density="compact"
            hide-details
            class="flex-1"
          />
          <v-btn v-if="evidenceItems.length > 1" icon="mdi-close" variant="text" size="small" @click="evidenceItems.splice(idx, 1)" />
        </div>
        <v-btn variant="text" size="small" @click="addRow" prepend-icon="mdi-plus">Add Evidence</v-btn>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('cancel')">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :disabled="!isValid" @click="submit">Submit & Complete</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { Task, EvidenceSubmission } from '../api/tasks'

const props = defineProps<{
  modelValue: boolean
  task: Task | null
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  submit: [evidence: EvidenceSubmission[]]
  cancel: []
}>()

const evidenceItems = ref<{ type: string; url: string }[]>([])

const missingTypes = computed(() => {
  if (!props.task) return []
  const submitted = new Set(props.task.evidence.map(e => e.type))
  return props.task.required_evidence_types.filter(t => !submitted.has(t))
})

const missingTypeOptions = computed(() =>
  missingTypes.value.map(t => ({ title: t.replace('_', ' '), value: t }))
)

const isValid = computed(() =>
  evidenceItems.value.length > 0 &&
  evidenceItems.value.every(i => i.type && i.url) &&
  missingTypes.value.every(t => evidenceItems.value.some(i => i.type === t))
)

watch(() => props.modelValue, (v) => {
  if (v) {
    evidenceItems.value = missingTypes.value.map(t => ({ type: t, url: '' }))
  }
})

function addRow() {
  evidenceItems.value.push({ type: '', url: '' })
}

function submit() {
  emit('submit', evidenceItems.value.map(i => ({ type: i.type, url: i.url })))
}
</script>
