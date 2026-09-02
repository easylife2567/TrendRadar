<script setup>
/*
 * 情感分析 /sentiment（design/04 §3.5，US-5）
 * 表单 → POST run（数秒到数十秒，长超时）→ 环形图 + 平台堆叠 + 代表标题 + AI 摘要
 * AI 可信度协议（10 §9）：AiBadge + .ai-container 左缘竖线 + 相对时间戳 + 模型名
 * AI 失败显式报错（502/429 由 client toast 常驻），不冒充缓存
 */
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { api } from '../api/client'
import { useI18n } from '../composables/useI18n'
import { useDateRange } from '../composables/useDateRange'
import { fmtRelTime } from '../utils/time'
import AiBadge from '../components/AiBadge.vue'
import EmptyState from '../components/EmptyState.vue'

// ECharts 重 chunk 异步加载（04 §6 首屏预算）
const TrendChart = defineAsyncComponent(() => import('../components/TrendChart.vue'))

const { t } = useI18n()
const { range, presets } = useDateRange('最近7天')

const topic = ref('')
const limit = ref(50)
const running = ref(false)
const result = ref(null) // run 端点 data
const history = ref([])

/* run 耗时数十秒：独立于全局 8s 弱网超时 */
async function run() {
  running.value = true
  result.value = null
  try {
    const body = { limit: limit.value }
    if (topic.value.trim()) body.topic = topic.value.trim()
    body.range = range.value
    result.value = await api.post('/api/analytics/sentiment/run', body, { timeout: 180000 })
    loadHistory()
  } catch {
    /* 502/429 显式报错已 toast 常驻 */
  } finally {
    running.value = false
  }
}

async function loadHistory() {
  try {
    const d = await api.get('/api/analytics/sentiment/results?limit=20', { silent: true })
    history.value = d?.results || []
  } catch {
    history.value = []
  }
}

onMounted(loadHistory)

function viewHistory(row) {
  result.value = { ...row, summary: row.summary || {} }
}

/* ---- 情感分布环形图 ---- */
const distOption = computed(() => {
  const d = result.value?.result?.distribution
  if (!d) return null
  const data = [
    { name: t('sentiment.positive'), value: d.positive || 0 },
    { name: t('sentiment.negative'), value: d.negative || 0 },
    { name: t('sentiment.neutral'), value: d.neutral || 0 },
  ]
  if (!data.some((x) => x.value > 0)) return null
  return {
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '44%'],
        data,
        // 语义色（10 §2.3）：正面 --sem-pos / 负面 --sem-neg / 中性 --text-muted
        itemStyle: { color: (p) => ['var(--sem-pos)', 'var(--sem-neg)', 'var(--text-muted)'][p.dataIndex] },
        label: { formatter: '{b}: {c}' },
      },
    ],
    tooltip: { trigger: 'item' },
  }
})

/* ---- 平台情感堆叠柱 ---- */
const platformOption = computed(() => {
  const rows = result.value?.result?.platform_breakdown || []
  if (!rows.length) return null
  const names = rows.map((r) => r.platform)
  return {
    grid: { left: 40, right: 16, top: 36, bottom: 28, containLabel: true },
    legend: { top: 0 },
    xAxis: { type: 'category', data: names, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { type: 'bar', name: t('sentiment.positive'), stack: 's', data: rows.map((r) => r.positive || 0), itemStyle: { color: 'var(--sem-pos)' }, barMaxWidth: 28 },
      { type: 'bar', name: t('sentiment.negative'), stack: 's', data: rows.map((r) => r.negative || 0), itemStyle: { color: 'var(--sem-neg)' } },
      { type: 'bar', name: t('sentiment.neutral'), stack: 's', data: rows.map((r) => r.neutral || 0), itemStyle: { color: 'var(--text-muted)' } },
    ],
    tooltip: { trigger: 'axis' },
  }
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">{{ t('sentiment.title') }}</h1>

    <form class="filters card" @submit.prevent="run">
      <input v-model="topic" class="input" type="search" :placeholder="t('sentiment.topicPlaceholder')" />
      <select v-model="range" class="select">
        <option v-for="p in presets" :key="p.value" :value="p.value">{{ p.label }}</option>
      </select>
      <select v-model.number="limit" class="select">
        <option :value="20">20</option>
        <option :value="50">50</option>
        <option :value="100">100</option>
      </select>
      <button class="btn btn-primary" type="submit" :disabled="running">
        {{ running ? t('sentiment.running') : t('sentiment.run') }}
      </button>
      <p class="micro-label hint-line">{{ t('sentiment.guardHint') }}</p>
    </form>

    <div v-if="running" class="card section running">
      <p>{{ t('sentiment.runningHint') }}</p>
    </div>

    <template v-if="result">
      <div class="card section ai-container">
        <header class="res-head">
          <h2>{{ t('sentiment.resultTitle', { kw: result.topic || t('sentiment.allTopics') }) }}</h2>
          <AiBadge :model="result.model" :at="result.created_at" />
        </header>

        <div class="charts">
          <div class="chart-box">
            <h3>{{ t('sentiment.distTitle') }}</h3>
            <TrendChart v-if="distOption" :option="distOption" :height="240" />
            <p v-else class="muted">—</p>
          </div>
          <div class="chart-box">
            <h3>{{ t('sentiment.platformTitle') }}</h3>
            <TrendChart v-if="platformOption" :option="platformOption" :height="240" />
            <p v-else class="muted">{{ t('sentiment.noPlatform') }}</p>
          </div>
        </div>

        <p v-if="result.result?.summary" class="summary">{{ result.result.summary }}</p>

        <div class="samples">
          <div v-if="result.result?.positive_samples?.length">
            <h3 class="pos">{{ t('sentiment.positiveSamples') }}</h3>
            <ul><li v-for="s in result.result.positive_samples" :key="s">{{ s }}</li></ul>
          </div>
          <div v-if="result.result?.negative_samples?.length">
            <h3 class="neg">{{ t('sentiment.negativeSamples') }}</h3>
            <ul><li v-for="s in result.result.negative_samples" :key="s">{{ s }}</li></ul>
          </div>
        </div>
      </div>
    </template>

    <div v-if="history.length" class="card section">
      <h2>{{ t('sentiment.historyTitle') }}</h2>
      <ul class="history">
        <li v-for="(h, i) in history" :key="i">
          <button class="history-row" @click="viewHistory(h)">
            <span class="kw">{{ h.topic || t('sentiment.allTopics') }}</span>
            <span class="mono-num range">{{ h.date_start }} ~ {{ h.date_end }}</span>
            <span class="mono-num time">{{ fmtRelTime(h.created_at) }}</span>
          </button>
        </li>
      </ul>
    </div>

    <EmptyState v-if="!result && !running && !history.length" :text="t('sentiment.empty')" :hint="t('sentiment.emptyHint')" />
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
  align-items: center;
  margin-bottom: var(--sp-4);
}

.filters .input {
  flex: 1;
  min-width: 200px;
}

.hint-line {
  width: 100%;
}

.running p {
  color: var(--text-secondary);
  margin: 0;
}

.section h2 {
  font-size: var(--text-lg);
  margin-bottom: var(--sp-3);
}

.res-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-3);
  flex-wrap: wrap;
}

.res-head h2 {
  margin-bottom: 0;
}

.charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-4);
  margin: var(--sp-4) 0;
}

@media (max-width: 900px) {
  .charts {
    grid-template-columns: 1fr;
  }
}

.chart-box h3 {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--sp-2);
}

.summary {
  font-size: var(--text-sm);
  line-height: 1.7;
  color: var(--text-primary);
  background: var(--bg-raised);
  border-radius: var(--radius-ctrl);
  padding: var(--sp-3);
}

.samples {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-4);
  margin-top: var(--sp-4);
}

@media (max-width: 900px) {
  .samples {
    grid-template-columns: 1fr;
  }
}

.samples h3 {
  font-size: var(--text-sm);
  margin: 0 0 var(--sp-2);
}

.samples h3.pos {
  color: var(--sem-pos);
}

.samples h3.neg {
  color: var(--sem-neg);
}

.samples ul {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: var(--text-sm);
}

.samples li {
  padding: var(--sp-1) 0;
  border-bottom: 1px dashed var(--border-subtle);
}

.history {
  list-style: none;
  margin: 0;
  padding: 0;
}

.history-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: 100%;
  padding: var(--sp-2) var(--sp-2);
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  border-radius: var(--radius-ctrl);
  text-align: left;
}

.history-row:hover {
  background: var(--bg-raised);
}

.kw {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.range,
.time {
  color: var(--text-secondary);
  font-size: var(--text-xs);
  flex: none;
}

.muted {
  color: var(--text-muted);
  font-size: var(--text-sm);
  margin: 0;
}
</style>
