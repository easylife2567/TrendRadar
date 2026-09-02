<script setup>
/*
 * 平台 tab（design/04 §3.2）。
 * platforms: [{id, name, count?}]；v-model 选中 id（'' = 全部）
 */
import { computed } from 'vue'

const props = defineProps({
  platforms: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
  allLabel: { type: String, default: '' },
})
defineEmits(['update:modelValue'])

const tabs = computed(() => [{ id: '', name: props.allLabel, count: 0 }, ...props.platforms])
</script>

<template>
  <div class="ptabs" role="tablist">
    <button
      v-for="p in tabs"
      :key="p.id"
      role="tab"
      class="ptab"
      :class="{ active: modelValue === p.id }"
      @click="$emit('update:modelValue', p.id)"
    >
      {{ p.name }}
      <span v-if="p.count" class="count mono-num">{{ p.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.ptabs {
  display: flex;
  gap: var(--sp-1);
  flex-wrap: wrap;
}

.ptab {
  height: 32px;
  padding: 0 var(--sp-3);
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  transition:
    color 150ms ease-out,
    border-color 150ms ease-out,
    background 150ms ease-out;
}

.ptab:hover {
  color: var(--text-primary);
  border-color: var(--border-strong);
}

.ptab.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.count {
  font-size: var(--text-xs);
  margin-left: 2px;
}
</style>
