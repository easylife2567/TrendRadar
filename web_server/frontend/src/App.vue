<script setup>
/*
 * 布局壳（design/04 §2 / 10 §6）：
 * - 桌面：左侧 220px 侧导航（「监测中心」八页 + 「工作台」组预留）+ 顶栏
 * - 移动 <768px：侧导航收起，底部 tab（四主页面）
 * - 顶栏：全局搜索框（回车跳 /search）、主题、语言
 * - toast 容器右上角（10 §6）
 */
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { dismissToast, toasts } from './api/client'
import { useI18n } from './composables/useI18n'

const { t, locale, setLocale } = useI18n()
const route = useRoute()
const router = useRouter()

const searchQuery = ref('')

// 主题（10 §2：dark 默认，index.html 内联已定初始值，这里切换+持久化）
const theme = ref(document.documentElement.dataset.theme || 'dark')

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
  localStorage.setItem('trendradar_theme', theme.value)
}

function toggleLocale() {
  setLocale(locale.value === 'zh-CN' ? 'en' : 'zh-CN')
}

function submitSearch() {
  const q = searchQuery.value.trim()
  if (!q) return
  router.push({ path: '/search', query: { q } })
  searchQuery.value = ''
}

watch(
  () => route.query.q,
  (q) => {
    if (q) searchQuery.value = ''
  }
)

const monitorNav = [
  { to: '/dashboard', key: 'nav.dashboard', icon: '◧' },
  { to: '/live', key: 'nav.live', icon: '≡' },
  { to: '/topics', key: 'nav.topics', icon: '◈' },
  { to: '/search', key: 'nav.search', icon: '⌕' },
  { to: '/sentiment', key: 'nav.sentiment', icon: '◐' },
  { to: '/compare', key: 'nav.compare', icon: '⇄' },
  { to: '/reports', key: 'nav.reports', icon: '▤' },
  { to: '/system', key: 'nav.system', icon: '⚙' },
]

const mobileNav = monitorNav.filter((n) => ['/dashboard', '/live', '/search', '/reports'].includes(n.to))
</script>

<template>
  <div class="layout">
    <!-- 侧导航（桌面） -->
    <aside class="sidebar">
      <div class="logo">
        <span class="logo-mark"></span>
        <span class="logo-text">TrendRadar</span>
      </div>

      <p class="micro-label group">{{ t('app.groupMonitor') }}</p>
      <nav class="nav">
        <RouterLink v-for="n in monitorNav" :key="n.to" :to="n.to" class="nav-item" active-class="active">
          <span class="icon" aria-hidden="true">{{ n.icon }}</span>
          <span>{{ t(n.key) }}</span>
        </RouterLink>
      </nav>

      <p class="micro-label group">{{ t('app.groupWorkbench') }}</p>
      <div class="nav-item disabled">
        <span class="icon" aria-hidden="true">▦</span>
        <span>{{ t('app.comingSoon') }}</span>
      </div>
    </aside>

    <div class="main-col">
      <!-- 顶栏 -->
      <header class="topbar">
        <form class="search" @submit.prevent="submitSearch">
          <input
            v-model="searchQuery"
            class="input"
            type="search"
            :placeholder="t('topbar.searchPlaceholder')"
            aria-label="global search"
          />
        </form>
        <div class="actions">
          <button class="icon-btn" :title="t('topbar.theme')" @click="toggleTheme">
            {{ theme === 'dark' ? '☾' : '☀' }}
          </button>
          <button class="icon-btn lang" :title="t('topbar.language')" @click="toggleLocale">
            {{ locale === 'zh-CN' ? 'EN' : '中' }}
          </button>
        </div>
      </header>

      <main class="content">
        <RouterView v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </Transition>
        </RouterView>
      </main>
    </div>

    <!-- 底部 tab（移动） -->
    <nav class="mobile-tabbar">
      <RouterLink v-for="n in mobileNav" :key="n.to" :to="n.to" class="tab" active-class="active">
        <span class="icon" aria-hidden="true">{{ n.icon }}</span>
        <span class="tab-text">{{ t(n.key) }}</span>
      </RouterLink>
    </nav>

    <!-- toast（10 §6：右上角堆叠） -->
    <div class="toast-stack" aria-live="polite">
      <div v-for="item in toasts" :key="item.id" class="toast" :class="item.type" @click="dismissToast(item.id)">
        {{ item.message }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}

/* ---- 侧导航（10 §6：220px，分组微标签，当前项左缘 3px accent） ---- */
.sidebar {
  width: var(--sidebar-width);
  flex: none;
  border-right: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  padding: var(--sp-4);
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-6);
}

.logo-mark {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: var(--gradient-brand);
}

.logo-text {
  font-weight: 700;
  font-size: var(--text-base);
}

.group {
  margin: var(--sp-4) 0 var(--sp-2);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 6px var(--sp-3);
  border-radius: var(--radius-ctrl);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  border-left: 3px solid transparent;
  transition:
    background 150ms ease-out,
    color 150ms ease-out;
}

a.nav-item:hover {
  background: var(--bg-raised);
  color: var(--text-primary);
}

a.nav-item.active {
  background: var(--bg-raised);
  border-left-color: var(--accent);
  color: var(--text-primary);
}

.nav-item.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.icon {
  width: 18px;
  text-align: center;
  flex: none;
}

/* ---- 主列 ---- */
.main-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  height: var(--topbar-height);
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  padding: 0 var(--sp-6);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  position: sticky;
  top: 0;
  z-index: 10;
}

.search {
  flex: 1;
  max-width: 420px;
}

.search .input {
  width: 100%;
}

.actions {
  margin-left: auto;
  display: flex;
  gap: var(--sp-2);
}

.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-ctrl);
  border: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-secondary);
  transition:
    color 150ms ease-out,
    border-color 150ms ease-out;
}

.icon-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.icon-btn.lang {
  width: auto;
  padding: 0 var(--sp-2);
  font-size: var(--text-xs);
}

.content {
  flex: 1;
}

/* ---- 移动端 ---- */
.mobile-tabbar {
  display: none;
}

@media (max-width: 767px) {
  .sidebar {
    display: none;
  }

  .topbar {
    padding: 0 var(--sp-4);
  }

  .content {
    padding-bottom: 60px; /* 底部 tab 高度 */
  }

  .mobile-tabbar {
    display: flex;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 56px;
    background: var(--bg-surface);
    border-top: 1px solid var(--border-subtle);
    z-index: 20;
  }

  .tab {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    color: var(--text-muted);
    font-size: 11px;
    text-decoration: none;
  }

  .tab .icon {
    font-size: 16px;
  }

  .tab.active {
    color: var(--accent);
  }
}

/* ---- toast ---- */
.toast-stack {
  position: fixed;
  top: var(--sp-4);
  right: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  z-index: 100;
  max-width: min(360px, 80vw);
}

.toast {
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--radius-ctrl);
  font-size: var(--text-sm);
  background: var(--bg-raised);
  border: 1px solid var(--border-strong);
  box-shadow: var(--shadow-overlay);
  cursor: pointer;
  animation: toast-in 200ms cubic-bezier(0.16, 1, 0.3, 1);
}

.toast.error {
  border-left: 3px solid var(--sem-neg);
}

@keyframes toast-in {
  from {
    transform: translateY(-8px);
    opacity: 0;
  }
  to {
    transform: none;
    opacity: 1;
  }
}

/* ---- 页面切换（10 §7：≤300ms 淡入位移 8px） ---- */
.page-enter-active {
  transition:
    opacity 200ms ease-out,
    transform 200ms ease-out;
}

.page-leave-active {
  transition: opacity 120ms ease-out;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-leave-to {
  opacity: 0;
}
</style>
