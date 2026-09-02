<script setup>
/*
 * 话题追踪 /topics/:keyword?（design/04 §3.3，US-4）
 * 「特斯拉近 30 天热度怎么变的」一屏可答：热度面积图 + 生命周期标注 +
 * 平台关注度环形图 + 相关新闻标题
 * 数据：topic-trend(trend) + topic-trend(lifecycle) + compare-platforms
 */
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import { useI18n } from '../composables/useI18n'
import { useDateRange } from '../composables/useDateRange'
import EmptyState from '../components/EmptyState.vue'

// ECharts 重 chunk 异步加载（04 §6 首屏预算）
const TrendChart = defineAsyncComponent(() => import('../components/TrendChart.vue'))

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { range, presets } = useDateRange('最近7天')

const keyword = ref('')
const loading = ref(false)
const searched = ref(false)
const trend = ref([]) // [{date, count, sample_titles}]
const lifecycle = ref(null) // {lifecycle_data, analysis}
const platformStats = ref(null) // {platform_stats, total_platforms}
const failed = ref(false)

async function load() {
  const kw = keyword.value.trim()
  if (!kw) return
  if (route.params.keyword !== kw) {
    // 同步 URL（history 直链可分享）
    router.replace({ path: `/topics/${encodeURIComponent(kw)}` })
  }
  loading.value = true
  failed.value = false
  try {
    const qs = `topic=${encodeURIComponent(kw)}&range=${encodeURIComponent(range.value)}`
    // 三源独立容错：一挂不拖垮整页
    const [tr, lc, cp] = await Promise.all([
      api.get(`/api/analytics/topic-trend?${qs}&analysis_type=trend`, { silent: true }).catch(() => null),
      api.get(`/api/analytics/topic-trend?${qs}&analysis_type=lifecycle`, { silent: true }).catch(() => null),
      api.get(`/api/analytics/compare-platforms?topic=${encodeURIComponent(kw)}&range=${encodeURIComponent(range.value)}`, { silent: true }).catch(() => null),
    ])
    if (tr) trend.value = tr || []
    if (lc) lifecycle.value = lc
    if (cp) platformStats.value = cp
    searched.value = true
    if (!tr && !lc) failed.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (route.params.keyword) {
    keyword.value = decodeURIComponent(String(route.params.keyword))
    load()
  }
})

// 顶栏搜索/其他页跳转带入（:keyword 变化）
watch(
  () => route.params.keyword,
  (kw) => {
    if (kw && decodeURIComponent(String(kw)) !== keyword.value) {
      keyword.value = decodeURIComponent(String(kw))
      load()
    }
  }
)

const totalMentions = computed(() => trend.value.reduce((s, x) => s + (x.count || 0), 0))

/* ---- 热度面积图 + 生命周期峰值标注 ---- */
const trendOption = computed(() => {
  if (!trend.value.length) return null
  const peak = lifecycle.value?.analysis?.peak_date
  return {
    grid: { left: 40, right: 16, top: 32, bottom: 28, containLabel: true },
    xAxis: { type: 'category', data: trend.value.map((x) => x.date.slice(5)) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        type: 'line',
        name: t('topics.mentions'),
        data: trend.value.map((x) => x.count),
        smooth: true,
        symbolSize: 5,
        areaStyle: { opacity: 0.12 },
        lineStyle: { width: 2 },
        ...(peak
          ? {
              markLine: {
                silent: true,
                symbol: 'none',
                label: { formatter: t('topics.peak'), fontSize: 11 },
                lineStyle: { type: 'dashed' },
                data: [{ xAxis: trend.value.findIndex((x) => x.date === peak) }].filter((p) => p.xAxis >= 0),
              },
            }
          : {}),
      },
    ],
    tooltip: { trigger: 'axis' },
  }
})

/* ---- 生命周期指标 ---- */
const life = computed(() => lifecycle.value?.analysis || null)

/* ---- 平台关注度环形图（话题被提及数按平台占比） ---- */
const platformOption = computed(() => {
  const stats = platformStats.value?.platform_stats || {}
  const entries = Object.entries(stats)
    .map(([name, s]) => ({ name, value: s.topic_mentions || 0 }))
    .filter((e) => e.value > 0)
    .sort((a, b) => b.value - a.value)
  if (!entries.length) return null
  return {
    legend: { bottom: 0, type: 'scroll' },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'], // 环形（10 §2.3）
        center: ['50%', '44%'],
        data: entries,
        label: { formatter: '{b} {d}%' },
      },
    ],
    tooltip: { trigger: 'item' },
  }
})

const sampleTitles = computed(() => {
  const seen = new Set()
  const out = []
  for (const day of trend.value) {
    for (const s of day.sample_titles || []) {
      if (!seen.has(s)) {
        seen.add(s)
        out.push(s)
      }
    }
  }
  return out.slice(0, 12)
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">{{ t('topics.title') }}</h1>

    <form class="filters" @submit.prevent="load">
      <input v-model="keyword" class="input q" type="search" :placeholder="t('topics.queryPlaceholder')" />
      <select v-model="range" class="select" @change="keyword.trim() && load()">
        <option v-for="p in presets" :key="p.value" :value="p.value">{{ p.label }}</option>
      </select>
      <button class="btn btn-primary" type="submit" :disabled="loading || !keyword.trim()">
        {{ t('topics.submit') }}
      </button>
    </form>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>

    <EmptyState v-else-if="!searched" :text="t('topics.empty')" :hint="t('topics.emptyHint')" />

    <EmptyState v-else-if="failed" :text="t('topics.noData')" :hint="t('topics.noDataHint')" />

    <template v-else>
      <p class="stat-line mono-num">
        {{ t('topics.statLine', { kw: keyword, n: totalMentions, days: trend.length }) }}
      </p>

      <div class="card section">
        <h2>{{ t('topics.trendTitle') }}</h2>
        <TrendChart v-if="trendOption" :option="trendOption" :height="300" />
        <p v-else class="muted">—</p>
      </div>

      <div class="two-col">
        <div class="card section">
          <h2>{{ t('topics.lifecycleTitle') }}</h2>
          <template v-if="life">
            <dl class="life-grid">
              <div><dt>{{ t('topics.firstSeen') }}</dt><dd class="mono-num">{{ life.first_appearance || '—' }}</dd></div>
              <div><dt>{{ t('topics.peakDay') }}</dt><dd class="mono-num">{{ life.peak_date || '—' }}</dd></div>
              <div><dt>{{ t('topics.peakCount') }}</dt><dd class="mono-num">{{ life.peak_count ?? '—' }}</dd></div>
              <div><dt>{{ t('topics.lastSeen') }}</dt><dd class="mono-num">{{ life.last_appearance || '—' }}</dd></div>
            </dl>
          </template>
          <p v-else class="muted">{{ t('topics.noLifecycle') }}</p>
        </div>

        <div class="card section">
          <h2>{{ t('topics.platformTitle') }}</h2>
          <TrendChart v-if="platformOption" :option="platformOption" :height="260" />
          <p v-else class="muted">{{ t('topics.noPlatformMentions') }}</p>
        </div>
      </div>

      <div v-if="sampleTitles.length" class="card section">
        <h2>{{ t('topics.relatedNews') }}</h2>
        <ul class="titles">
          <li v-for="s in sampleTitles" :key="s">{{ s }}</li>
        </ul>
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

.stat-line {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--sp-3);
}

.section h2 {
  font-size: var(--text-lg);
  margin-bottom: var(--sp-3);
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-4);
  margin-top: var(--sp-4);
}

@media (max-width: 900px) {
  .two-col {
    grid-template-columns: 1fr;
  }
}

.life-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--sp-3);
  margin: 0;
}

.life-grid dt {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-bottom: 2px;
}

.life-grid dd {
  margin: 0;
  font-size: var(--text-base);
}

.titles {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: var(--text-sm);
}

.titles li {
  padding: var(--sp-2) 0;
  border-bottom: 1px dashed var(--border-subtle);
}

.titles li:last-child {
  border-bottom: none;
}

.muted {
  color: var(--text-muted);
  font-size: var(--text-sm);
  margin: 0;
}

.loading {
  padding: var(--sp-12);
  text-align: center;
  color: var(--text-secondary);
}
</style>
