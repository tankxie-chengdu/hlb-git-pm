import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    component: () => import('../components/AppLayout.vue'),
    children: [
      { path: '', name: 'Dashboard', component: () => import('../views/DashboardView.vue') },
      { path: 'repos', name: 'Repos', component: () => import('../views/ReposView.vue') },
      { path: 'members', name: 'Members', component: () => import('../views/MembersView.vue') },
      { path: 'recipients', name: 'Recipients', component: () => import('../views/RecipientsView.vue') },
      { path: 'schedules', name: 'Schedules', component: () => import('../views/SchedulesView.vue') },
      { path: 'reports', name: 'Reports', component: () => import('../views/ReportsView.vue') },
      { path: 'reports/:id', name: 'ReportDetail', component: () => import('../views/ReportDetailView.vue'), props: true },
      { path: 'reports/trigger', name: 'ReportTrigger', component: () => import('../views/ReportTriggerView.vue') }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn) {
    return '/login'
  }
})

export default router
