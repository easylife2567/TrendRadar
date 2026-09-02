<script setup>
/*
 * P3 页面占位（/topics /sentiment /compare /system）
 * 路由结构现在就位（04 §2 避免日后导航大改），Step 9 落地真实页面
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from '../composables/useI18n'
import EmptyState from '../components/EmptyState.vue'

const route = useRoute()
const { t } = useI18n()

const title = computed(() => {
  const key = Object.keys(route.params).length ? '/topics' : route.path
  const map = {
    '/topics': 'nav.topics',
    '/sentiment': 'nav.sentiment',
    '/compare': 'nav.compare',
    '/system': 'nav.system',
  }
  return t(map[key] || 'nav.dashboard')
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">{{ title }}</h1>
    <div class="card">
      <EmptyState :text="t('placeholder.title')" :hint="t('placeholder.hint')" />
    </div>
  </div>
</template>

<style scoped>
.page-title {
  font-size: var(--text-xl);
  margin-bottom: var(--sp-4);
}
</style>
