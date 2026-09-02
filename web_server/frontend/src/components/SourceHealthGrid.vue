<script setup>
/*
 * 源健康灯板（design/04 §3.1 / 10 §6 状态灯）
 * platforms: {platform_id: {platform_name?, success, failed}}（/api/system/health/sources 的 data.platforms）
 * 灯色：全成功 pos 绿 / 混合 warn 黄 / 全失败 crit 红
 */
import { computed } from 'vue'

const props = defineProps({
  platforms: { type: Object, default: () => ({}) },
})

const lights = computed(() =>
  Object.entries(props.platforms).map(([id, s]) => {
    const ok = s.success || 0
    const bad = s.failed || 0
    const level = bad === 0 ? 'ok' : ok > 0 ? 'warn' : 'crit'
    return { id, name: s.platform_name || id, ok, bad, level }
  })
)
</script>

<template>
  <div class="health-grid">
    <div
      v-for="l in lights"
      :key="l.id"
      class="light"
      :title="`${l.name} ✓${l.ok} ✗${l.bad}`"
    >
      <span class="dot" :class="l.level"></span>
      <span class="name">{{ l.name }}</span>
      <span class="nums mono-num">✓{{ l.ok }} ✗{{ l.bad }}</span>
    </div>
    <p v-if="!lights.length" class="empty-hint">—</p>
  </div>
</template>

<style scoped>
.health-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--sp-2);
}

.light {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--text-xs);
  padding: var(--sp-1) var(--sp-2);
  border-radius: var(--radius-ctrl);
  background: var(--bg-base);
}

.dot.ok {
  background: var(--sem-pos);
}

.dot.warn {
  background: var(--sem-warn);
}

.dot.crit {
  background: var(--sem-crit);
  /* 10 §7：仅 warn/crit 态允许呼吸，2s 周期 */
  animation: breathe 2s ease-in-out infinite;
}

.name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
}

.nums {
  color: var(--text-secondary);
  font-size: 11px;
}

.empty-hint {
  color: var(--text-muted);
  margin: 0;
}

@keyframes breathe {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}
</style>
