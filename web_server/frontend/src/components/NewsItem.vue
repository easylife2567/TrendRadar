<script setup>
/*
 * 热榜条目（design/04 §3.2 / 10 §6）
 * - 热度分级延续报告页语义：rank 1-3 = top（crit 红），4-10 = high（warn 橙），其余灰
 * - NEW 徽标：count === 1（仅出现于一次抓取 ≈ 今日新上榜，MVP 近似）
 * - 排名升降：MVP 无基线数据，不做 ▲▼（P3 话题页接入 rank-history 对比后启用）
 */
import { computed } from 'vue'
import { useI18n } from '../composables/useI18n'

const props = defineProps({
  item: { type: Object, required: true }, // {id,title,platform,platform_name,rank,avg_rank,count,url?}
  highlight: { type: String, default: '' }, // 关键词高亮（关注词命中）
})
defineEmits(['open'])

const { t } = useI18n()

const grade = computed(() => {
  const r = props.item.rank
  if (r >= 1 && r <= 3) return 'top'
  if (r >= 4 && r <= 10) return 'high'
  return 'normal'
})

const isNew = computed(() => props.item.count === 1)

// 标题关键词高亮：分段渲染，命中段加 <mark>
const titleParts = computed(() => {
  const title = props.item.title || ''
  const kw = (props.highlight || '').trim()
  if (!kw) return [{ text: title, hit: false }]
  const parts = []
  let rest = title
  let k = kw.toLowerCase()
  while (rest) {
    const idx = rest.toLowerCase().indexOf(k)
    if (idx < 0) {
      parts.push({ text: rest, hit: false })
      break
    }
    if (idx > 0) parts.push({ text: rest.slice(0, idx), hit: false })
    parts.push({ text: rest.slice(idx, idx + kw.length), hit: true })
    rest = rest.slice(idx + kw.length)
  }
  return parts
})
</script>

<template>
  <div class="news-item" @click="$emit('open', item)">
    <span class="rank-num mono-num" :class="grade">{{ item.rank }}</span>
    <div class="body">
      <div class="title-line">
        <span class="title">
          <template v-for="(p, i) in titleParts" :key="i">
            <mark v-if="p.hit">{{ p.text }}</mark>
            <template v-else>{{ p.text }}</template>
          </template>
        </span>
        <span v-if="isNew" class="badge new">{{ t('live.newBadge') }}</span>
      </div>
      <div class="meta">
        <span class="platform">{{ item.platform_name || item.platform }}</span>
        <span v-if="item.count" class="count mono-num">{{ item.count }}{{ t('live.countSuffix') }}</span>
        <span v-if="item.avg_rank" class="mono-num">avg {{ item.avg_rank }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.news-item {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background 150ms ease-out;
}

.news-item:last-child {
  border-bottom: none;
}

.news-item:hover {
  background: var(--bg-raised);
}

.rank-num {
  flex: none;
  min-width: 24px;
  text-align: center;
  font-size: var(--text-xs);
  font-weight: 700;
  padding: 2px 6px;
  border-radius: var(--radius-pill);
  color: #fff;
  background: var(--text-muted);
  margin-top: 2px;
}

.rank-num.top {
  background: var(--sem-crit);
}

.rank-num.high {
  background: var(--sem-warn);
}

.body {
  flex: 1;
  min-width: 0;
}

.title-line {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
}

.title {
  font-size: var(--text-sm);
  line-height: 1.4;
}

.title mark {
  background: rgba(251, 191, 36, 0.25); /* --sem-warn 浅底 */
  color: inherit;
  border-radius: 2px;
  padding: 0 1px;
}

.badge.new {
  flex: none;
  background: var(--sem-info);
  color: #fff;
}

.meta {
  display: flex;
  gap: var(--sp-3);
  margin-top: 2px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
</style>
