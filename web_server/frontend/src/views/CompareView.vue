<script setup>
/*
 * 对比分析 /compare（design/04 §3.6，US-6）
 * 时期对比（overview 电梯数 + topic_shift 升降榜 + platform_activity）+ 平台对比柱图
 * 数据：compare-periods(overview/topic_shift/platform_activity) + compare-platforms
 */
import { computed, defineAsyncComponent, ref } from 'vue'
import { api } from '../api/client'
import { useI18n } from '../composables/useI18n'
import EmptyState from '../components/EmptyState.vue'

// ECharts 重 chunk 异步加载（04 §6 首屏预算）
const TrendChart = defineAsyncComponent(() => import('../components/TrendChart.vue'))

const { t } = useI18n()

function daysAgo(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

const dateA = ref(daysAgo(1))
const dateB = ref(daysAgo(0))
const topic = ref('')

const loading = ref(false)
const searched = ref(false)
const overview = ref(null)
const shift = ref(null)
const activity = ref(null)
const byPlatform = ref(null)

async function load() {
  loading.value = true
  try {
    const qs = `period_a=${dateA.value}&period_b=${dateB.value}`
    const tq = topic.value.trim() ? `&topic=${encodeURIComponent(topic.value.trim())}` : ''
    const [ov, sh, ac, bp] = await Promise.all([
      api.get(`/api/analytics/compare-periods?${qs}&compare_type=overview${tq}`, { silent: true }).catch(() => null),
      api.get(`/api/analytics/compare-periods?${qs}&compare_type=topic_shift${tq}`, { silent: true }).catch(() => null),
      api.get(`/api/analytics/compare-periods?${qs}&compare_type=platform_activity${tq}`, { silent: true }).catch(() => null),
      topic.value.trim()
        ? api.get(`/api/analytics/compare-platforms?topic=${encodeURIComponent(topic.value.trim())}&start=${dateA.value}&end=${dateB.value}`, { silent: true }).catch(() => null)
        : Promise.resolve(null),
    ])
    overview.value = ov
    shift.value = sh
    activity.value = ac
    byPlatform.value = bp
    searched.value = true
  } finally {
    loading.value = false
  }
}

load() /* 初次进入即用默认近两天对比 */

const changeText = computed(() => overview.value?.overview?.count_change_percent ?? '—')
const changeUp = computed(() => {
  const s = String(changeText.value)
  return !s.startsWith('-') && s !== '0.0%' && s !== '—'
})

/* 平台活跃度柱图 */
const activityOption = computed(() => {
  const rows = activity.value?.platform_comparison || []
  if (!rows.length) return null
  const names = rows.map((r) => r.platform || r.platform_id)
  return {
    grid: { left: 40, right: 16, top: 36, bottom: 28, containLabel: true },
    legend: { top: 0 },
    xAxis: { type: 'category', data: names, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' },
    series: [
      { type: 'bar', name: t('compare.periodA'), data: rows.map((r) => r.period1_count ?? 0), barMaxWidth: 24 },
      { type: 'bar', name: t('compare.periodB'), data: rows.map((r) => r.period2_count ?? 0), barMaxWidth: 24 },
    ],
    tooltip: { trigger: 'axis' },
  }
})

/* 平台关注度柱图（话题提及） */
const byPlatformOption = computed(() => {
  const stats = byPlatform.value?.platform_stats || {}
  const entries = Object.entries(stats).map(([name, s]) => ({ name, v: s.topic_mentions || 0 }))
  if (!entries.length) return null
  entries.sort((a, b) => b.v - a.v)
  return {
    grid: { left: 40, right: 16, top: 16, bottom: 48, containLabel: true },
    xAxis: { type: 'category', data: entries.map((e) => e.name), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', name: t('topics.mentions'), data: entries.map((e) => e.v), barMaxWidth: 24 }],
    tooltip: { trigger: 'axis' },
  }
})

const rising = computed(() => shift.value?.rising_topics || [])
const falling = computed(() => shift.value?.falling_topics || [])
const newTopics = computed(() => shift.value?.new_topics || [])
const newKeywords = computed(() => overview.value?.keyword_analysis?.new_keywords || [])
const disappearedKeywords = computed(() => overview.value?.keyword_analysis?.disappeared_keywords || [])
</script>

<template>
  <div class="page">
    <h1 class="page-title">{{ t('compare.title') }}</h1>

    <form class="filters card" @submit.prevent="load">
      <label class="field">
        <span class="micro-label">{{ t('compare.periodA') }}</span>
        <input v-model="dateA" class="input" type="date" />
      </label>
      <label class="field">
        <span class="micro-label">{{ t('compare.periodB') }}</span>
        <input v-model="dateB" class="input" type="date" />
      </label>
      <input v-model="topic" class="input" type="search" :placeholder="t('compare.topicPlaceholder')" />
      <button class="btn btn-primary" type="submit" :disabled="loading">{{ t('compare.submit') }}</button>
    </form>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>

    <template v-else-if="searched">
      <!-- 总量电梯 -->
      <div class="card section delta-card">
        <p class="micro-label">{{ t('compare.totalDelta') }}</p>
        <p class="delta mono-num" :class="{ up: changeUp, down: !changeUp }">{{ changeText }}</p>
        <p class="sub mono-num">
          {{ t('compare.counts', { a: overview?.overview?.period1_count ?? '—', b: overview?.overview?.period2_count ?? '—' }) }}
        </p>
      </div>

      <div class="two-col">
        <!-- 升降榜 -->
        <div class="card section">
          <h2>{{ t('compare.shiftTitle') }}</h2>
          <div class="shift-cols">
            <div>
              <h3 class="pos">{{ t('compare.rising') }}</h3>
              <ul class="kw-list">
                <li v-for="x in rising" :key="'r' + (x.keyword || x)">
                  <span>{{ x.keyword || x }}</span>
                  <span v-if="x.change_percent" class="mono-num" :class="String(x.change_percent).startsWith('-') ? 'down' : 'up'">{{ x.change_percent }}</span>
                </li>
                <li v-if="!rising.length" class="muted">—</li>
              </ul>
            </div>
            <div>
              <h3 class="neg">{{ t('compare.falling') }}</h3>
              <ul class="kw-list">
                <li v-for="x in falling" :key="'f' + (x.keyword || x)">
                  <span>{{ x.keyword || x }}</span>
                  <span v-if="x.change_percent" class="mono-num">{{ x.change_percent }}</span>
                </li>
                <li v-if="!falling.length" class="muted">—</li>
              </ul>
            </div>
            <div>
              <h3>{{ t('compare.newTopics') }}</h3>
              <ul class="kw-list">
                <li v-for="x in newTopics" :key="'n' + (x.keyword || x)">{{ x.keyword || x }}</li>
                <li v-if="!newTopics.length" class="muted">—</li>
              </ul>
            </div>
          </div>
        </div>

        <!-- 平台活跃度 -->
        <div class="card section">
          <h2>{{ t('compare.activityTitle') }}</h2>
          <TrendChart v-if="activityOption" :option="activityOption" :height="260" />
          <p v-else class="muted">—</p>
        </div>
      </div>

      <!-- 新增/消失关键词 -->
      <div class="card section">
        <h2>{{ t('compare.keywordsTitle') }}</h2>
        <div class="shift-cols">
          <div>
            <h3 class="pos">{{ t('compare.newKeywords') }}</h3>
            <p class="kw-line mono-num">{{ newKeywords.slice(0, 20).join('、') || '—' }}</p>
          </div>
          <div>
            <h3 class="neg">{{ t('compare.disappearedKeywords') }}</h3>
            <p class="kw-line mono-num">{{ disappearedKeywords.slice(0, 20).join('、') || '—' }}</p>
          </div>
        </div>
      </div>

      <!-- 平台关注度（有话题时） -->
      <div v-if="byPlatformOption" class="card section">
        <h2>{{ t('compare.byPlatformTitle') }}</h2>
        <TrendChart :option="byPlatformOption" :height="240" />
      </div>

      <EmptyState
        v-if="!overview && !shift && !activity"
        :text="t('compare.noData')"
        :hint="t('compare.noDataHint')"
      />
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
  align-items: end;
  margin-bottom: var(--sp-4);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field .input {
  width: 150px;
}

.filters .input[type='search'] {
  flex: 1;
  min-width: 180px;
}

.section h2 {
  font-size: var(--text-lg);
  margin-bottom: var(--sp-3);
}

.delta-card {
  text-align: center;
}

.delta {
  font-size: var(--text-2xl);
  margin: var(--sp-1) 0;
}

.delta.up {
  color: var(--sem-pos);
}

.delta.down {
  color: var(--sem-neg);
}

.sub {
  color: var(--text-secondary);
  font-size: var(--text-xs);
  margin: 0;
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

.shift-cols {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--sp-3);
}

@media (max-width: 600px) {
  .shift-cols {
    grid-template-columns: 1fr;
  }
}

.shift-cols h3 {
  font-size: var(--text-sm);
  margin: 0 0 var(--sp-2);
}

h3.pos {
  color: var(--sem-pos);
}

h3.neg {
  color: var(--sem-neg);
}

.kw-list {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: var(--text-sm);
}

.kw-list li {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-2);
  padding: 4px 0;
  border-bottom: 1px dashed var(--border-subtle);
}

.up {
  color: var(--sem-pos);
}

.down {
  color: var(--sem-neg);
}

.kw-line {
  font-size: var(--text-sm);
  line-height: 1.8;
  margin: 0;
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
