<template>
  <div class="ag-theme-alpine" style="width: 100%; flex: 1;">
    <AgGridVue
      :rowData="tasks"
      :columnDefs="columnDefs"
      :defaultColDef="defaultColDef"
      :getRowId="getRowId"
      row-selection="single"
      @row-clicked="onRowClicked"
      style="width: 100%; height: 100%;"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import type { ColDef, RowClickedEvent, GetRowIdParams } from 'ag-grid-community'
import type { Task } from '../api/tasks'
import type { Project } from '../api/projects'
import { PRIORITY_LABELS, STATUS_LABELS, type Status } from '../stores/tasks'

interface User {
  id: string
  display_name?: string
  email: string
}

const props = defineProps<{
  tasks: Task[]
  projects: Project[]
  users: User[]
}>()

const emit = defineEmits<{
  select: [task: Task]
}>()

const projectMap = computed(() => new Map(props.projects.map(p => [p.id, p.name])))
const userMap = computed(() => new Map(props.users.map(u => [u.id, u.display_name || u.email])))

const defaultColDef: ColDef = {
  sortable: true,
  filter: true,
  resizable: true,
}

const columnDefs: ColDef[] = [
  { field: 'title', headerName: 'Title', flex: 2 },
  { field: 'type', headerName: 'Type', width: 100 },
  {
    field: 'priority',
    headerName: 'Priority',
    width: 110,
    valueFormatter: (p: any) => PRIORITY_LABELS[p.value] || p.value,
  },
  {
    field: 'status',
    headerName: 'Status',
    width: 130,
    valueFormatter: (p: any) => STATUS_LABELS[p.value as Status] || p.value,
  },
  {
    field: 'project_ids',
    headerName: 'Projects',
    flex: 1,
    valueFormatter: (p: any) => (p.value as string[]).map(id => projectMap.value.get(id) || '').filter(Boolean).join(', '),
  },
  {
    field: 'assignee_ids',
    headerName: 'Assignees',
    flex: 1,
    valueFormatter: (p: any) => (p.value as string[]).map(id => userMap.value.get(id) || '').filter(Boolean).join(', '),
  },
  {
    field: 'created_at',
    headerName: 'Created',
    width: 140,
    valueFormatter: (p: any) => new Date(p.value).toLocaleDateString(),
  },
]

function getRowId(params: GetRowIdParams) {
  return params.data.id
}

function onRowClicked(event: RowClickedEvent) {
  if (event.data) emit('select', event.data as Task)
}
</script>

<style>
@import 'ag-grid-community/styles/ag-grid.css';
@import 'ag-grid-community/styles/ag-theme-alpine.css';
</style>
