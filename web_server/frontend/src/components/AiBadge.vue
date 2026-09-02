<script setup>
/*
 * 「AI 生成」可信度徽标（design/10 §9 可信度视觉协议）
 * 用法：<AiBadge :model="'gpt-4o'" :at="1717300000" />
 * 容器左缘 2px --sem-info 竖线由使用方的 AI 容器 class 承担（.ai-container）
 */
import { computed } from 'vue'
import { fmtAbsTime, fmtRelTime } from '../utils/time'

const props = defineProps({
  model: { type: String, default: '' },
  at: { type: [Number, String], default: '' }, // 生成时间戳（秒 / ISO / "YYYY-MM-DD HH:MM:SS"）
})

const rel = computed(() => fmtRelTime(props.at))
const abs = computed(() => fmtAbsTime(props.at))
</script>

<template>
  <span class="ai-badge-wrap">
    <span class="badge ai">
      <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
        <path d="M8 0l1.8 4.7L14.5 6 9.8 7.8 8 12.5 6.2 7.8 1.5 6l4.7-1.3L8 0z" />
        <circle cx="13" cy="12.5" r="1.6" />
      </svg>
      AI
    </span>
    <span v-if="at" class="at" :title="abs">{{ rel }}</span>
    <span v-if="model" class="model">{{ model }}</span>
  </span>
</template>

<style scoped>
.ai-badge-wrap {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  vertical-align: middle;
}

.badge.ai {
  border: 1px solid var(--sem-info); /* --sem-info 描边空心（10 §6） */
  color: var(--sem-info);
  gap: 3px;
}

.at,
.model {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
</style>
