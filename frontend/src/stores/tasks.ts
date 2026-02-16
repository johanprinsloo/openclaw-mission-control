import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  listTasks,
  createTask,
  transitionTask,
  getTask,
  updateTask,
  type Task,
  type TaskFilters,
  type EvidenceSubmission,
} from '../api/tasks'

export const STATUSES = ['backlog', 'in-progress', 'in-review', 'complete'] as const
export type Status = typeof STATUSES[number]

export const STATUS_LABELS: Record<Status, string> = {
  'backlog': 'Backlog',
  'in-progress': 'In Progress',
  'in-review': 'In Review',
  'complete': 'Complete',
}

export const STATUS_COLORS: Record<Status, string> = {
  'backlog': '#6B7280',
  'in-progress': '#3B82F6',
  'in-review': '#F59E0B',
  'complete': '#10B981',
}

export const PRIORITY_COLORS: Record<string, string> = {
  critical: '#DC2626',
  high: '#EF4444',
  medium: '#F59E0B',
  low: '#10B981',
}

export const PRIORITY_LABELS: Record<string, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref<Task[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const filters = ref<TaskFilters>({})

  const tasksByStatus = computed(() => {
    const map: Record<string, Task[]> = {}
    for (const status of STATUSES) {
      map[status] = tasks.value.filter(t => t.status === status)
    }
    return map
  })

  async function fetchTasks(orgSlug: string) {
    loading.value = true
    error.value = null
    try {
      tasks.value = await listTasks(orgSlug, filters.value)
    } catch (e: any) {
      error.value = e.response?.data?.detail ?? e.message
    } finally {
      loading.value = false
    }
  }

  async function create(orgSlug: string, body: Parameters<typeof createTask>[1]) {
    const task = await createTask(orgSlug, body)
    tasks.value.push(task)
    return task
  }

  async function transition(
    orgSlug: string,
    taskId: string,
    toStatus: string,
    evidence: EvidenceSubmission[] = [],
  ) {
    const updated = await transitionTask(orgSlug, taskId, { to_status: toStatus, evidence })
    const idx = tasks.value.findIndex(t => t.id === taskId)
    if (idx !== -1) tasks.value[idx] = updated
    return updated
  }

  async function update(orgSlug: string, taskId: string, body: Parameters<typeof updateTask>[2]) {
    const updated = await updateTask(orgSlug, taskId, body)
    const idx = tasks.value.findIndex(t => t.id === taskId)
    if (idx !== -1) tasks.value[idx] = updated
    return updated
  }

  async function refresh(orgSlug: string, taskId: string) {
    const updated = await getTask(orgSlug, taskId)
    const idx = tasks.value.findIndex(t => t.id === taskId)
    if (idx !== -1) tasks.value[idx] = updated
    return updated
  }

  function setFilters(newFilters: TaskFilters) {
    filters.value = { ...newFilters }
  }

  // SSE event handler
  function handleEvent(event: { type: string; payload: any }) {
    const { type, payload } = event

    if (type === 'task.created') {
      const existing = tasks.value.find(t => t.id === payload.task_id)
      if (!existing) {
        tasks.value.push({
          id: payload.task_id,
          org_id: '',
          title: payload.title,
          description: null,
          type: 'chore',
          priority: payload.priority || 'medium',
          status: payload.status || 'backlog',
          required_evidence_types: [],
          project_ids: payload.project_ids || [],
          assignee_ids: payload.assignee_ids || [],
          dependency_ids: [],
          evidence: [],
          completed_at: null,
          archived_at: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
      }
    }

    if (type === 'task.transitioned') {
      const idx = tasks.value.findIndex(t => t.id === payload.task_id)
      if (idx !== -1) {
        tasks.value[idx] = { ...tasks.value[idx], status: payload.to_status }
      }
    }

    if (type === 'task.updated') {
      const idx = tasks.value.findIndex(t => t.id === payload.task_id)
      if (idx !== -1) {
        const { task_id, ...updates } = payload
        tasks.value[idx] = { ...tasks.value[idx], ...updates }
      }
    }
  }

  return {
    tasks,
    loading,
    error,
    filters,
    tasksByStatus,
    fetchTasks,
    create,
    transition,
    update,
    refresh,
    setFilters,
    handleEvent,
  }
})
