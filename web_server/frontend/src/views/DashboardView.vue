<script setup>
/*
 * 仪表盘 /dashboard（design/04 §3.1，US-1）
 * viral 预警条 → 四指标卡 → 关注词曲线 → TOP 话题 + 源灯板 + predict 预测卡
 * 数据：status / trending / viral / health/sources / news-date / keyword-series / predict
 * 注：predict 为统计趋势预测（tools 层线性增长率），非 AI 产出 → 不挂 AI 徽标
 * （design/10 §9 可信度协议；计划原文假设其带 AI 徽标，记为 P3 偏差）
 */
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useI18n } from '../composables/useI18n'
import { usePolling } from '../composables/usePolling'

// ECharts 重 chunk 异步加载：不阻塞首屏渲染（04 §6 首屏预算）
const TrendChart = defineAsyncComponent(() => import('../components/TrendChart.vue'))
import SourceHealthGrid from '../components/SourceHealthGrid.vue'
import EmptyState from '../components/EmptyState.vue'
import { hhmm } from '../utils/time'

const { t } = useI18n()
const router = useRouter()

const loading = ref(true)
const status = ref(null)
const trending = ref(null)
const viral = ref([])
const health = ref(null)
const todayCount = ref(null)
const series = ref(null) // {buckets, series:[{word, counts}]}
const predicted = ref([])

const today = new Date().toISOString().slice(0, 10)

async function fetchOne() {
  // 各源独立容错：一挂不拖垮整页（toast 由 client 弹）
  const jobs = [
    api.get('/api/system/status', { silent: true }).then((d) => (status.value = d)).catch(() => {}),
    api.get('/api/topics/trending?top_n=20', { silent: true }).then((d) => (trending.value = d)).catch(() => {}),
    api.get('/api/analytics/viral', { silent: true }).then((d) => (viral.value = d || [])).catch(() => {}),
    api.get('/api/system/health/sources', { silent: true }).then((d) => (health.value = d)).catch(() => {}),
    api.get(`/api/news/date/${today}?limit=1000`, { silent: true }).then((d) => (todayCount.value = d?.length ?? null)).catch(() => {}),
    api.get('/api/analytics/predict?lookahead_hours=6', { silent: true }).then((d) => (predicted.value = d || [])).catch(() => {}),
    keywordSeriesJob(),
  ]
  await Promise.all(jobs)
}

// 关注词曲线：取 trending top5 词 → keyword-series（design/07 差异#11 下沉查询）
async function keywordSeriesJob() {
  try {
    const tr = await api.get('/api/topics/trending?top_n=5', { silent: true })
    trending.value = tr
    const words = (tr?.topics || []).map((x) => x.keyword).filter(Boolean).slice(0, 5)
    if (words.length) {
      const q = encodeURIComponent(words.join(','))
      series.value = await api.get(`/api/topics/keyword-series?words=${q}&granularity=hour`, { silent: true })
    }
  } catch {
    /* 忽略 */
  }
}

const { stale, refresh } = usePolling(fetchOne, 60000)

onMounted(async () => {
  await fetchOne()
  loading.value = false
})

/* ---- 指标卡 ---- */

const platformStats = computed(() => {
  const platforms = health.value?.platforms || {}
  const ids = Object.keys(platforms)
  const ok = ids.filter((id) => (platforms[id]?.success || 0) > 0).length
  return { ok, total: ids.length }
})

const keywordHits = computed(() =>
  (trending.value?.topics || []).reduce((sum, x) => sum + (x.matched_news || 0), 0)
)

const freshness = computed(() => {
  const crawls = health.value?.crawls || []
  const last = crawls.length ? crawls[crawls.length - 1]?.crawl_time : ''
  return last ? hhmm(last) : '—'
})

/* ---- 图表 ---- */

const curveOption = computed(() => {
  if (!series.value?.buckets?.length) return null
  return {
    grid: { left: 40, right: 16, top: 36, bottom: 28, containLabel: true },
    legend: { top: 0 },
    xAxis: { type: 'category', data: series.value.buckets },
    yAxis: { type: 'value' },
    series: series.value.series.map((s) => ({
      type: 'line',
      name: s.word,
      data: s.counts,
      smooth: true,
      symbolSize: 4,
      areaStyle: { opacity: 0.08 },
    })),
    tooltip: { trigger: 'axis' },
  }
})

const topics = computed(() => (trending.value?.topics || []).slice(0, 10))
</script>

<template>
  <div class="page full">
    <!-- viral 预警条（04 §3.1：命中才出现，置顶，页面唯一允许"喊"的元素） -->
    <div v-if="viral.length" class="viral-bar" role="alert">
      <span class="viral-label">{{ t('dashboard.viralAlert') }}</span>
      <button v-for="v in viral" :key="v.keyword" class="viral-item" @click="router.push(`/topics/${encodeURIComponent(v.keyword)}`)">
        {{ v.keyword }} <span class="mono-num">×{{ v.current_count }}</span>
        <span class="level">{{ v.alert_level }}</span>
      </button>
    </div>

    <h1 class="page-title">{{ t('dashboard.title') }}</h1>
    <span v-if="stale" class="stale-hint">{{ t('topbar.stale') }}</span>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>

    <template v-else>
      <!-- 四指标卡（10 §4：≥1200 四列 / ≥768 双列 / 单列） -->
      <div class="kpis">
        <div class="card kpi">
          <p class="micro-label">{{ t('dashboard.newsCount') }}</p>
          <p class="value mono-num">{{ todayCount ?? '—' }}</p>
          <p class="sub">{{ t('dashboard.items') }}</p>
        </div>
        <div class="card kpi">
          <p class="micro-label">{{ t('dashboard.keywordHits') }}</p>
          <p class="value mono-num">{{ keywordHits || '—' }}</p>
          <p class="sub">{{ t('dashboard.hits') }}</p>
        </div>
        <div class="card kpi">
          <p class="micro-label">{{ t('dashboard.platformsOnline') }}</p>
          <p class="value mono-num">{{ platformStats.total ? platformStats.ok : '—' }}</p>
          <p class="sub">{{ t('dashboard.online', platformStats) }}</p>
        </div>
        <div class="card kpi">
          <p class="micro-label">{{ t('dashboard.freshness') }}</p>
          <p class="value mono-num">{{ freshness }}</p>
          <p class="sub">{{ t('dashboard.lastCrawl', { time: '' }) }}</p>
        </div>
      </div>

      <!-- 关注词曲线 -->
      <div class="card section">
        <h2>{{ t('dashboard.keywordCurve') }}</h2>
        <TrendChart v-if="curveOption" :option="curveOption" :height="280" />
        <EmptyState v-else :text="t('live.empty')" />
      </div>

      <div class="two-col">
        <!-- TOP 话题榜 -->
        <div class="card section">
          <h2>{{ t('dashboard.topTopics') }}</h2>
          <ol class="topic-list">
            <li v-for="(topic, i) in topics" :key="topic.keyword">
              <button class="topic-row" @click="router.push(`/topics/${encodeURIComponent(topic.keyword)}`)">
                <span class="mono-num idx">{{ i + 1 }}</span>
                <span class="kw">{{ topic.keyword }}</span>
                <span class="mono-num freq">{{ topic.frequency }}</span>
              </button>
            </li>
          </ol>
          <p v-if="!topics.length" class="muted">—</p>
        </div>

        <!-- 源健康灯板 + predict 占位 -->
        <div class="col">
          <div class="card section">
            <h2>{{ t('dashboard.sourceHealth') }}</h2>
            <SourceHealthGrid :platforms="health?.platforms || {}" />
          </div>

          <!-- predict 预测卡：统计趋势预测，非 AI 产出（不挂徽标，10 §9） -->
          <div class="card section">
            <h2>{{ t('dashboard.predictTitle') }}</h2>
            <p v-if="!predicted.length" class="muted">{{ t('dashboard.predictEmpty') }}</p>
            <ol v-else class="topic-list">
              <li v-for="p in predicted.slice(0, 5)" :key="p.keyword">
                <button class="topic-row" @click="router.push(`/topics/${encodeURIComponent(p.keyword)}`)">
                  <span class="kw">{{ p.keyword }}</span>
                  <span class="mono-num freq">+{{ p.growth_rate }}%</span>
                </button>
              </li>
            </ol>
            <p class="micro-label">{{ t('dashboard.predictNote') }}</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.full {
  max-width: none; /* 04 §3.1 仪表盘全宽流式 */
}

.page-title {
  font-size: var(--text-xl);
  margin: var(--sp-4) 0;
}

.viral-bar {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
  padding: var(--sp-2) var(--sp-4);
  border-radius: var(--radius-card);
  background: rgba(251, 113, 133, 0.12); /* --sem-crit 浅底 */
  border: 1px solid var(--sem-crit);
  margin-bottom: var(--sp-2);
}

.viral-label {
  color: var(--sem-crit);
  font-weight: 700;
  font-size: var(--text-sm);
}

.viral-item {
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: var(--radius-ctrl);
}

.viral-item:hover {
  background: rgba(251, 113, 133, 0.2);
}

.level {
  font-size: var(--text-xs);
  color: var(--sem-crit);
  margin-left: 2px;
}

.stale-hint {
  font-size: var(--text-xs);
  color: var(--sem-warn);
}

.kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--sp-4);
  margin-bottom: var(--sp-4);
}

@media (max-width: 1199px) {
  .kpis {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 767px) {
  .kpis {
    grid-template-columns: 1fr;
  }
}

.kpi .value {
  font-size: var(--text-2xl);
  line-height: 1.2;
  margin: var(--sp-1) 0;
}

.kpi .sub {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
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

.col {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.topic-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.topic-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: 100%;
  padding: 6px var(--sp-2);
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  border-radius: var(--radius-ctrl);
  transition: background 150ms ease-out;
  text-align: left;
}

.topic-row:hover {
  background: var(--bg-raised);
}

.idx {
  color: var(--text-muted);
  width: 20px;
  flex: none;
}

.kw {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.freq {
  color: var(--text-secondary);
  font-size: var(--text-xs);
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
