import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useOrgStore } from '../src/stores/orgs'

describe('Org Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('initializes with empty state', () => {
    const store = useOrgStore()
    expect(store.orgs).toEqual([])
    expect(store.activeOrg).toBeNull()
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('activeOrgSlug is null when no active org', () => {
    const store = useOrgStore()
    expect(store.activeOrgSlug).toBeNull()
  })
})
