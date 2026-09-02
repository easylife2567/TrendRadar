<script setup>
/*
 * 全历史检索 /search（design/04 §3.4，US-3）
 * 单输入框 + 模式 + range 快捷词；结果列表 + 侧栏聚合（日期/平台分布，前端聚合）
 */
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import { useI18n } from '../composables/useI18n'
import { useDateRange } from '../composables/useDateRange'
import EmptyState from '../components/EmptyState.vue'
import NewsItem from '../components/NewsItem.vue'

// ECharts 重 chunk 异步加载（04 §6 首屏预算）
const TrendChart = defineAsyncComponent(() => import('../components/TrendChart.vue'))

const { t } = useI18n()
const route = useRoute()

const query = ref('')
const mode = ref('keyword')
const { range, presets } = useDateRange('最近30天')
const results = ref([])
const searched = ref(false)
const loading = ref(false)

const modes = [
  { value: 'keyword', label: computed(() => t('search.modeKeyword')) },
  { value: 'fuzzy', label: computed(() => t('search.modeFuzzy')) },
  { value: 'entity', label: computed(() => t('search.modeEntity')) },
]

async function runSearch() {
  const q = query.value.trim()
  if (!q) return
  loading.value = true
  try {
    const params = new URLSearchParams({ query: q, search_mode: mode.value, range: range.value, limit: '100' })
    results.value = (await api.get(`/api/news/search?${params}`)) || []
    searched.value = true
  } catch {
    /* toast 已弹 */
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  // 顶栏全局搜索跳转带入
  const q = route.query.q
  if (q) {
    query.value = String(q)
    runSearch()
  }
})

/* ---- 侧栏聚合（基于返回结果集） ---- */

const dateDist = computed(() => {
  const map = new Map()
  for (const r of results.value) {
    map.set(r.date, (map.get(r.date) || 0) + (r.count || 1))
  }
  const entries = [...map.entries()].sort()
  return {
    xAxis: { type: 'category', data: entries.map(([d]) => d.slice(5)) },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: entries.map(([, n]) => n), barMaxWidth: 24 }],
    tooltip: { trigger: 'axis' },
    grid: { left: 32, right: 8, top: 16, bottom: 24, containLabel: true },
  }
})

const platformDist = computed(() => {
  const map = new Map()
  for (const r of results.value) {
    map.set(r.platform_name || r.platform, (map.get(r.platform_name || r.platform) || 0) + (r.count || 1))
  }
  const entries = [...map.entries()].sort((a, b) => b[1] - a[1])
  return {
    xAxis: { type: 'category', data: entries.map(([p]) => p), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: entries.map(([, n]) => n), barMaxWidth: 24 }],
    tooltip: { trigger: 'axis' },
    grid: { left: 32, right: 8, top: 16, bottom: 48, containLabel: true },
  }
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">{{ t('search.title') }}</h1>

    <form class="filters" @submit.prevent="runSearch">
      <input
        v-model="query"
        class="input q"
        type="search"
        :placeholder="t('search.queryPlaceholder')"
      />
      <div class="mode-switch">
        <button
          v-for="m in modes"
          :key="m.value"
          type="button"
          class="btn btn-sm"
          :class="mode === m.value ? 'btn-primary' : 'btn-secondary'"
          @click="mode = m.value"
        >
          {{ m.label.value }}
        </button>
      </div>
      <select v-model="range" class="select">
        <option v-for="p in presets" :key="p.value" :value="p.value">{{ p.label }}</option>
      </select>
      <button class="btn btn-primary" type="submit" :disabled="loading">
        {{ t('search.submit') }}
      </button>
    </form>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>

    <template v-else-if="searched">
      <EmptyState v-if="!results.length" :text="t('search.empty')" :hint="t('search.emptyHint')" />

      <div v-else class="results-layout">
        <div class="main">
          <p class="result-count mono-num">{{ t('search.results', { n: results.length }) }}</p>
          <div class="card list">
            <NewsItem v-for="r in results" :key="r.platform + r.title" :item="{ ...r, rank: r.rank || 0 }" :highlight="query" />
          </div>
        </div>
        <aside class="side">
          <div class="card">
            <h3>{{ t('search.dateDist') }}</h3>
            <TrendChart :option="dateDist" :height="200" />
          </div>
          <div class="card">
            <h3>{{ t('search.platformDist') }}</h3>
            <TrendChart :option="platformDist" :height="220" />
          </div>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page-title {
  font-size: var(--text-xl);
  margin-bottom: var(--sp-4);
}

.filters {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
  margin-bottom: var(--sp-4);
}

.q {
  flex: 1;
  min-width: 220px;
}

.mode-switch {
  display: flex;
  gap: var(--sp-1);
}

.results-layout {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: var(--sp-4);
}

@media (max-width: 900px) {
  .results-layout {
    grid-template-columns: 1fr;
  }
}

.result-count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--sp-2);
}

.list {
  padding: var(--sp-2) 0;
}

.side {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.side h3 {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--sp-2);
}

.loading {
  padding: var(--sp-12);
  text-align: center;
  color: var(--text-secondary);
}
</style>
