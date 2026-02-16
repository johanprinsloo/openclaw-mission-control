import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  listProjects,
  createProject,
  transitionProject,
  deleteProject,
  type Project,
} from '../api/projects'

export const STAGES = [
  'definition', 'poc', 'development', 'testing', 'launch', 'maintenance',
] as const

export type Stage = typeof STAGES[number]

export const STAGE_LABELS: Record<Stage, string> = {
  definition: 'Definition',
  poc: 'POC',
  development: 'Development',
  testing: 'Testing',
  launch: 'Launch',
  maintenance: 'Maintenance',
}

export const STAGE_COLORS: Record<Stage, string> = {
  definition: '#8B5CF6',
  poc: '#F59E0B',
  development: '#3B82F6',
  testing: '#10B981',
  launch: '#EF4444',
  maintenance: '#6B7280',
}

export const useProjectStore = defineStore('projects', () => {
  const projects = ref<Project[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const projectsByStage = computed(() => {
    const map: Record<string, Project[]> = {}
    for (const stage of STAGES) {
      map[stage] = projects.value.filter(p => p.stage === stage)
    }
    return map
  })

  async function fetchProjects(orgSlug: string) {
    loading.value = true
    error.value = null
    try {
      projects.value = await listProjects(orgSlug)
    } catch (e: any) {
      error.value = e.response?.data?.detail ?? e.message
    } finally {
      loading.value = false
    }
  }

  async function create(orgSlug: string, body: { name: string; type: string; description?: string; owner_id?: string }) {
    const project = await createProject(orgSlug, body)
    projects.value.push(project)
    return project
  }

  async function transition(orgSlug: string, projectId: string, toStage: string) {
    const updated = await transitionProject(orgSlug, projectId, toStage)
    const idx = projects.value.findIndex(p => p.id === projectId)
    if (idx !== -1) projects.value[idx] = updated
    return updated
  }

  async function remove(orgSlug: string, projectId: string) {
    await deleteProject(orgSlug, projectId)
    projects.value = projects.value.filter(p => p.id !== projectId)
  }

  // SSE event handler
  function handleEvent(event: { type: string; payload: any }) {
    const { type, payload } = event

    if (type === 'project.created') {
      // Refetch to get full project data with task counts
      const existing = projects.value.find(p => p.id === payload.project_id)
      if (!existing) {
        // Add a placeholder that will be replaced on next fetch
        projects.value.push({
          id: payload.project_id,
          org_id: '',
          name: payload.name,
          type: payload.type || 'software',
          description: null,
          stage: payload.stage || 'definition',
          owner_id: payload.owner_id || null,
          links: {},
          task_count: 0,
          task_complete_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
      }
    }

    if (type === 'project.transitioned') {
      const idx = projects.value.findIndex(p => p.id === payload.project_id)
      if (idx !== -1) {
        projects.value[idx] = { ...projects.value[idx], stage: payload.to_stage }
      }
    }

    if (type === 'project.updated') {
      const idx = projects.value.findIndex(p => p.id === payload.project_id)
      if (idx !== -1) {
        const { project_id, ...updates } = payload
        projects.value[idx] = { ...projects.value[idx], ...updates }
      }
    }

    if (type === 'project.deleted') {
      projects.value = projects.value.filter(p => p.id !== payload.project_id)
    }
  }

  return {
    projects,
    loading,
    error,
    projectsByStage,
    fetchProjects,
    create,
    transition,
    remove,
    handleEvent,
  }
})
