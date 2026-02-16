import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/orgs',
      name: 'org-select',
      component: () => import('../views/OrgSelectView.vue'),
    },
    {
      path: '/orgs/:orgSlug',
      component: () => import('../layouts/OrgLayout.vue'),
      children: [
        {
          path: '',
          redirect: (to) => ({ path: `/orgs/${to.params.orgSlug}/projects` }),
        },
        {
          path: 'projects',
          name: 'projects',
          component: () => import('../views/PlaceholderView.vue'),
          meta: { title: 'Projects' },
        },
        {
          path: 'tasks',
          name: 'tasks',
          component: () => import('../views/PlaceholderView.vue'),
          meta: { title: 'Tasks' },
        },
        {
          path: 'settings',
          name: 'org-settings',
          component: () => import('../views/OrgSettingsView.vue'),
          meta: { title: 'Settings', requiresAdmin: true },
        },
        {
          path: 'settings/users',
          name: 'org-users',
          component: () => import('../views/UsersView.vue'),
          meta: { title: 'Users', requiresAdmin: true },
        },
      ],
    },
    {
      path: '/',
      redirect: '/orgs',
    },
  ],
})

export default router
