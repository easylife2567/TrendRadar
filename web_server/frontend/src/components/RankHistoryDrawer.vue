<script setup>
/*
 * 排名历史抽屉（design/04 §3.2 / 10 §6 抽屉规范）
 * 右滑入 min(480px, 90vw)，遮罩点击关闭；内容：排名折线 + 标题改动 + 原文链接
 */
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { api } from '../api/client'
import { useI18n } from '../composables/useI18n'
import { hhmm } from '../utils/time'

// ECharts 重 chunk 异步加载（04 §6 首屏预算）
const TrendChart = defineAsyncComponent(() => import('./TrendChart.vue'))

const props = defineProps({
  open: { type: Boolean, default: false },
  date: { type: String, required: true },
  item: { type: Object, default: null }, // news 条目（需 id / title）
})
const emit = defineEmits(['close'])

const { t } = useI18n()
const loading = ref(false)
const payload = ref(null) // {news, rank_history, title_changes}

const chartOption = computed(() => {
  const rh = payload.value?.rank_history || []
  if (!rh.length) return null
  return {
    grid: { left: 40, right: 16, top: 16, bottom: 28, containLabel: true },
    xAxis: {
      type: 'category',
      data: rh.map((p) => hhmm(p.crawl_time)),
    },
    yAxis: { type: 'value', inverse: true, min: 1 }, // 排名 1 在顶
    series: [
      {
        type: 'line',
        name: t('drawer.rankHistory'),
        data: rh.map((p) => p.rank),
        smooth: true,
        symbolSize: 5,
        lineStyle: { width: 2 },
      },
    ],
    tooltip: { trigger: 'axis' },
  }
})

const news = computed(() => payload.value?.news || {})
const changes = computed(() => payload.value?.title_changes || [])

watch(
  () => [props.open, props.item?.id],
  async ([open]) => {
    if (!open || !props.item?.id) return
    loading.value = true
    payload.value = null
    try {
      payload.value = await api.get(`/api/news/item/${props.date}/${props.item.id}/rank-history`)
    } catch {
      /* toast 已由 client 弹出 */
    } finally {
      loading.value = false
    }
  }
)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="mask" @click.self="emit('close')">
      <aside class="drawer" role="dialog" aria-modal="true">
        <header class="head">
          <h3 class="title">{{ item?.title }}</h3>
          <button class="btn btn-secondary btn-sm" @click="emit('close')">{{ t('common.close') }}</button>
        </header>

        <div v-if="loading" class="loading">{{ t('common.loading') }}</div>

        <template v-else-if="payload">
          <p class="stats mono-num">
            {{
              t('drawer.crawlStats', {
                count: news.crawl_count ?? '—',
                first: hhmm(news.first_crawl_time) || '—',
                last: hhmm(news.last_crawl_time) || '—',
              })
            }}
          </p>

          <section v-if="chartOption" class="section">
            <h4>{{ t('drawer.rankHistory') }}</h4>
            <TrendChart :option="chartOption" :height="220" />
          </section>

          <section class="section">
            <h4>{{ t('drawer.titleChanges') }}</h4>
            <p v-if="!changes.length" class="muted">{{ t('drawer.noChanges') }}</p>
            <ul v-else class="changes">
              <li v-for="(c, i) in changes" :key="i">
                <span class="mono-num time">{{ c.changed_at }}</span>
                <span>{{ c.new_title }}</span>
              </li>
            </ul>
          </section>

          <a
            v-if="news.url"
            class="source-link"
            :href="news.url"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ t('drawer.openSource') }} ↗
          </a>
        </template>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 60;
}

.drawer {
  position: absolute;
  top: 0;
  right: 0;
  height: 100%;
  width: min(480px, 90vw);
  background: var(--bg-raised);
  box-shadow: var(--shadow-overlay);
  padding: var(--sp-4);
  overflow-y: auto;
  animation: slide-in 200ms cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes slide-in {
  from {
    transform: translateX(24px);
    opacity: 0;
  }
  to {
    transform: none;
    opacity: 1;
  }
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
}

.title {
  font-size: var(--text-base);
  line-height: 1.5;
}

.stats {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: var(--sp-3) 0;
}

.section h4 {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--sp-4) 0 var(--sp-2);
}

.muted {
  color: var(--text-muted);
  font-size: var(--text-sm);
  margin: 0;
}

.changes {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: var(--text-sm);
}

.changes li {
  display: flex;
  gap: var(--sp-2);
  padding: var(--sp-1) 0;
  border-bottom: 1px dashed var(--border-subtle);
}

.time {
  color: var(--text-muted);
  flex: none;
}

.source-link {
  display: inline-block;
  margin-top: var(--sp-4);
  font-size: var(--text-sm);
}
</style>
