import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
    },
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
          component: () => import('../views/ProjectBoardView.vue'),
          meta: { title: 'Projects' },
        },
        {
          path: 'tasks',
          name: 'tasks',
          component: () => import('../views/TaskBoardView.vue'),
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
        {
          path: 'channels/:id',
          name: 'channel',
          component: () => import('../views/ChannelView.vue'),
          meta: { title: 'Channel' },
        },
      ],
    },
    {
      path: '/',
      redirect: '/login',
    },
  ],
})

export default router
