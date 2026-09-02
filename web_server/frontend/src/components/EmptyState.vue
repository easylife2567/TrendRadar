<script setup>
/*
 * 空态（design/10 §6：品牌渐变插画位 + 一句话 + 主操作按钮）
 */
defineProps({
  text: { type: String, required: true },
  hint: { type: String, default: '' },
  actionLabel: { type: String, default: '' },
})
defineEmits(['action'])
</script>

<template>
  <div class="empty">
    <div class="art" aria-hidden="true"></div>
    <p class="text">{{ text }}</p>
    <p v-if="hint" class="hint">{{ hint }}</p>
    <button v-if="actionLabel" class="btn btn-primary btn-sm" @click="$emit('action')">
      {{ actionLabel }}
    </button>
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-12) var(--sp-6);
  text-align: center;
}

.art {
  width: 96px;
  height: 36px;
  border-radius: var(--radius-pill);
  background: var(--gradient-brand);
  opacity: 0.85;
}

.text {
  margin: 0;
  font-size: var(--text-base);
  color: var(--text-primary);
}

.hint {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
</style>
