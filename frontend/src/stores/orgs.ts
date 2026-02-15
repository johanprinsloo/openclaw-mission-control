import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  listOrgs,
  createOrg,
  getOrg,
  updateOrg,
  deleteOrg,
  reactivateOrg,
  type OrgListItem,
  type OrgDetail,
} from '../api/organizations'

export const useOrgStore = defineStore('orgs', () => {
  const orgs = ref<OrgListItem[]>([])
  const activeOrg = ref<OrgDetail | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const activeOrgSlug = computed(() => activeOrg.value?.slug ?? null)

  async function fetchOrgs() {
    loading.value = true
    error.value = null
    try {
      orgs.value = await listOrgs()
    } catch (e: any) {
      error.value = e.response?.data?.detail ?? e.message
    } finally {
      loading.value = false
    }
  }

  async function selectOrg(slug: string) {
    loading.value = true
    error.value = null
    try {
      activeOrg.value = await getOrg(slug)
    } catch (e: any) {
      error.value = e.response?.data?.detail ?? e.message
    } finally {
      loading.value = false
    }
  }

  async function create(name: string, slug: string) {
    const org = await createOrg(name, slug)
    await fetchOrgs()
    return org
  }

  async function updateSettings(settings: Record<string, any>) {
    if (!activeOrg.value) return
    activeOrg.value = await updateOrg(activeOrg.value.slug, { settings })
  }

  async function updateName(name: string) {
    if (!activeOrg.value) return
    activeOrg.value = await updateOrg(activeOrg.value.slug, { name })
  }

  async function beginDeletion() {
    if (!activeOrg.value) return
    await deleteOrg(activeOrg.value.slug)
    await fetchOrgs()
  }

  async function cancelDeletion() {
    if (!activeOrg.value) return
    activeOrg.value = await reactivateOrg(activeOrg.value.slug)
    await fetchOrgs()
  }

  return {
    orgs,
    activeOrg,
    activeOrgSlug,
    loading,
    error,
    fetchOrgs,
    selectOrg,
    create,
    updateSettings,
    updateName,
    beginDeletion,
    cancelDeletion,
  }
})
