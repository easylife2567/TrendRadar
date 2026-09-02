/*
 * design/04 §2 路由表：路由级动态 import 分包（8 页各一 chunk，04 §6 性能预算）
 * P3 四页（topics/sentiment/compare/system）路由存在但为占位（Step 9 落地）
 */
import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    {
      path: '/dashboard',
      component: () => import('../views/DashboardView.vue'),
    },
    {
      path: '/live',
      component: () => import('../views/LiveView.vue'),
    },
    {
      path: '/topics/:keyword?',
      component: () => import('../views/PlaceholderView.vue'),
    },
    {
      path: '/search',
      component: () => import('../views/SearchView.vue'),
    },
    {
      path: '/sentiment',
      component: () => import('../views/PlaceholderView.vue'),
    },
    {
      path: '/compare',
      component: () => import('../views/PlaceholderView.vue'),
    },
    {
      path: '/reports',
      component: () => import('../views/ReportsView.vue'),
    },
    {
      path: '/system',
      component: () => import('../views/PlaceholderView.vue'),
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})
