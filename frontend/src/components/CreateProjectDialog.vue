<template>
  <v-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" max-width="500">
    <v-card>
      <v-card-title>Create Project</v-card-title>
      <v-card-text>
        <v-text-field
          v-model="form.name"
          label="Project Name"
          variant="outlined"
          density="compact"
          class="mb-3"
          :rules="[v => !!v || 'Name is required']"
        />
        <v-select
          v-model="form.type"
          :items="[
            { title: 'Software', value: 'software' },
            { title: 'Documentation', value: 'docs' },
            { title: 'Launch', value: 'launch' },
          ]"
          label="Type"
          variant="outlined"
          density="compact"
          class="mb-3"
        />
        <v-textarea
          v-model="form.description"
          label="Description"
          variant="outlined"
          density="compact"
          rows="3"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="$emit('update:modelValue', false)">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          @click="handleCreate"
          :loading="creating"
          :disabled="!form.name"
        >
          Create
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  created: [body: { name: string; type: string; description?: string }]
}>()

const creating = ref(false)
const form = reactive({ name: '', type: 'software', description: '' })

watch(() => props.modelValue, (open) => {
  if (open) {
    form.name = ''
    form.type = 'software'
    form.description = ''
  }
})

function handleCreate() {
  creating.value = true
  emit('created', {
    name: form.name,
    type: form.type,
    description: form.description || undefined,
  })
  creating.value = false
}
</script>
