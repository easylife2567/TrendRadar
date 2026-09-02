<script setup>
/*
 * 系统与健康 /system（design/04 §3.7，US-9/10）
 * 调度倒计时（get_next_schedule_run 三态降级）+ 手动抓取/管线按钮（🔑+二次确认）
 * + 源健康灯板 + 可用日期。
 * 文案注意（07 差异#13）：手动抓取成功后分析缓存将被清空；两按钮语义差异要写明。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, getStoredApiKey, setStoredApiKey, toast } from '../api/client'
import { useI18n } from '../composables/useI18n'
import { hhmm } from '../utils/time'
import SourceHealthGrid from '../components/SourceHealthGrid.vue'

const { t } = useI18n()

const schedule = ref(null)
const status = ref(null)
const dates = ref([])
const health = ref(null)

async function fetchAll() {
  const jobs = [
    api.get('/api/system/schedule', { silent: true }).then((d) => (schedule.value = d)).catch(() => {}),
    api.get('/api/system/status', { silent: true }).then((d) => (status.value = d)).catch(() => {}),
    api.get('/api/system/dates', { silent: true }).then((d) => (dates.value = d || [])).catch(() => {}),
    api.get('/api/system/health/sources', { silent: true }).then((d) => (health.value = d)).catch(() => {}),
  ]
  await Promise.all(jobs)
}

/* ---- 倒计时（schedule.enabled 时，next_period 每 30s 重算） ----
 * next_period = {key,name,start:"HH:MM",end,date:"YYYY-MM-DD"}（tools 层 _find_next_period） */
const countdown = ref('')
let timer = null

const nextTime = computed(() => {
  const np = schedule.value?.next_period
  if (!np?.start) return ''
  return np.date ? `${np.date} ${np.start}` : np.start
})

function tick() {
  const np = schedule.value?.next_period
  if (!np?.start || !/^\d{2}:\d{2}$/.test(np.start)) {
    countdown.value = ''
    return
  }
  const target = new Date(`${np.date || ''}T${np.start}:00`)
  if (Number.isNaN(target.getTime())) {
    countdown.value = ''
    return
  }
  const mins = Math.round((target.getTime() - Date.now()) / 60000)
  if (mins <= 0) {
    countdown.value = t('system.imminent')
    return
  }
  if (mins >= 1440) {
    countdown.value = t('system.countdownDays', { d: Math.floor(mins / 1440), h: Math.floor((mins % 1440) / 60) })
  } else if (mins >= 60) {
    countdown.value = t('system.countdownHours', { h: Math.floor(mins / 60), m: mins % 60 })
  } else {
    countdown.value = t('system.countdownMin', { n: mins })
  }
}

onMounted(async () => {
  await fetchAll()
  tick()
  timer = setInterval(tick, 30000)
})
onUnmounted(() => clearInterval(timer))

/* ---- 手动操作（🔑 + 二次确认） ---- */
const apiKey = ref(getStoredApiKey())
const busy = ref('')

function saveKey() {
  apiKey.value = apiKey.value.trim()
  setStoredApiKey(apiKey.value)
  if (apiKey.value) toast(t('system.keySaved'), { type: 'success' })
}

async function guardedAction(kind) {
  if (!getStoredApiKey()) {
    toast(t('system.needKey'), { type: 'error', sticky: true })
    return
  }
  const msg = kind === 'crawl' ? t('system.confirmCrawl') : t('system.confirmPipeline')
  if (!window.confirm(msg)) return
  busy.value = kind
  try {
    if (kind === 'crawl') {
      await api.post('/api/crawl/trigger', {}, { timeout: 120000 })
      toast(t('system.crawlStarted'), { type: 'success' })
    } else {
      await api.post('/api/pipeline/run', {}, { timeout: 30000 })
      toast(t('system.pipelineStarted'), { type: 'success' })
    }
  } catch {
    /* 409 运行中 / 401 key 错误 已 toast */
  } finally {
    busy.value = ''
    setTimeout(fetchAll, 1500)
  }
}

/* schedule 三态文案 */
const scheduleText = computed(() => {
  const s = schedule.value
  if (!s) return t('common.loading')
  if (s.enabled === false) return s.description || t('system.scheduleDisabled')
  if (s.reason === 'timeline_unavailable') return t('system.scheduleTimelineUnavailable')
  return s.description || t('system.scheduleOn')
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">{{ t('system.title') }}</h1>

    <div class="two-col">
      <!-- 调度倒计时 -->
      <div class="card section">
        <h2>{{ t('system.scheduleTitle') }}</h2>
        <p class="schedule-text">{{ scheduleText }}</p>
        <p v-if="nextTime && countdown" class="mono-num countdown">
          {{ t('system.nextRun', { time: nextTime }) }} · {{ countdown }}
        </p>
        <p v-if="schedule?.last_crawl_time" class="micro-label mono-num">
          {{ t('system.lastCrawl', { time: hhmm(schedule.last_crawl_time) }) }}
        </p>
      </div>

      <!-- 系统状态 -->
      <div class="card section">
        <h2>{{ t('system.statusTitle') }}</h2>
        <dl class="kv">
          <div v-if="status?.version">
            <dt>{{ t('system.version') }}</dt>
            <dd class="mono-num">{{ status.version }}</dd>
          </div>
          <template v-if="status?.cache">
            <div>
              <dt>{{ t('system.cacheEntries') }}</dt>
              <dd class="mono-num">{{ status.cache.size ?? status.cache.entries ?? '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('system.cacheHits') }}</dt>
              <dd class="mono-num">{{ status.cache.hits ?? '—' }}</dd>
            </div>
          </template>
          <template v-if="status?.storage">
            <div>
              <dt>{{ t('system.datesCount') }}</dt>
              <dd class="mono-num">{{ status.storage.available_dates ?? status.storage.dates ?? dates.length }}</dd>
            </div>
          </template>
        </dl>
      </div>
    </div>

    <!-- 手动操作（🔑 + 二次确认） -->
    <div class="card section">
      <h2>{{ t('system.actionsTitle') }}</h2>
      <div class="actions">
        <label class="key-field">
          <span class="micro-label">API Key</span>
          <input v-model="apiKey" class="input" type="password" autocomplete="off" :placeholder="t('system.keyPlaceholder')" @change="saveKey" />
        </label>
        <button class="btn btn-secondary" :disabled="busy === 'crawl'" @click="guardedAction('crawl')">
          🔑 {{ t('system.crawlBtn') }}
        </button>
        <button class="btn btn-secondary" :disabled="busy === 'pipeline'" @click="guardedAction('pipeline')">
          🔑 {{ t('system.pipelineBtn') }}
        </button>
      </div>
      <p class="micro-label">{{ t('system.actionsHint') }}</p>
    </div>

    <!-- 源健康灯板 -->
    <div class="card section">
      <h2>{{ t('dashboard.sourceHealth') }}</h2>
      <SourceHealthGrid v-if="health?.platforms && Object.keys(health.platforms).length" :platforms="health.platforms" />
      <p v-else class="muted">{{ t('system.noHealthData') }}</p>
    </div>

    <!-- 可用日期 -->
    <div class="card section">
      <h2>{{ t('system.datesTitle') }}</h2>
      <p v-if="!dates.length" class="muted">—</p>
      <div v-else class="date-chips">
        <span v-for="d in [...dates].reverse().slice(0, 30)" :key="d" class="chip mono-num">{{ d }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title {
  font-size: var(--text-xl);
  margin-bottom: var(--sp-4);
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-4);
  margin-bottom: var(--sp-4);
}

@media (max-width: 900px) {
  .two-col {
    grid-template-columns: 1fr;
  }
}

.section h2 {
  font-size: var(--text-lg);
  margin-bottom: var(--sp-3);
}

.schedule-text {
  color: var(--text-primary);
  font-size: var(--text-sm);
  margin: 0 0 var(--sp-2);
}

.countdown {
  font-size: var(--text-lg);
  color: var(--accent);
}

.kv {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--sp-3);
  margin: 0;
}

.kv dt {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-bottom: 2px;
}

.kv dd {
  margin: 0;
  font-size: var(--text-base);
}

.actions {
  display: flex;
  gap: var(--sp-3);
  flex-wrap: wrap;
  align-items: end;
  margin-bottom: var(--sp-2);
}

.key-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 220px;
}

.date-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-1);
}

.chip {
  padding: 2px var(--sp-2);
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-subtle);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.muted {
  color: var(--text-muted);
  font-size: var(--text-sm);
  margin: 0;
}
</style>
