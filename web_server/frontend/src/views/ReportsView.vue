<script setup>
/*
 * 报告归档 /reports（design/04 §3.7）
 * 日期网格（files 数 + 大小）→ 选中 iframe 嵌入 /api/reports/{date}/html
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import { useI18n } from '../composables/useI18n'
import EmptyState from '../components/EmptyState.vue'

const { t } = useI18n()

const loading = ref(true)
const reports = ref([]) // [{date, files:[{filename,size_bytes,modified_at}]}]
const selected = ref('')

async function fetchReports() {
  reports.value = (await api.get('/api/reports')) || []
  // latest 别名置顶，默认选中它
  if (reports.value.length) selected.value = reports.value[0].date
}

onMounted(async () => {
  try {
    await fetchReports()
  } catch {
    /* toast 已弹 */
  } finally {
    loading.value = false
  }
})

function fmtSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const selectedSrc = computed(() =>
  selected.value ? `/api/reports/${encodeURIComponent(selected.value)}/html` : ''
)

const isSelectedLatest = computed(() => selected.value === 'latest')
</script>

<template>
  <div class="page">
    <h1 class="page-title">{{ t('reports.title') }}</h1>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>

    <EmptyState v-else-if="!reports.length" :text="t('reports.empty')" :hint="t('reports.emptyHint')" />

    <template v-else>
      <div class="date-grid">
        <button
          v-for="r in reports"
          :key="r.date"
          class="date-card"
          :class="{ active: selected === r.date }"
          @click="selected = r.date"
        >
          <span v-if="r.date === 'latest'" class="badge latest">{{ t('reports.openLatest') }}</span>
          <span v-else class="date-text mono-num">{{ r.date }}</span>
          <span class="meta mono-num">{{ t('reports.files', { n: r.files.length }) }} · {{ fmtSize(r.files.reduce((s, f) => s + f.size_bytes, 0)) }}</span>
        </button>
      </div>

      <p v-if="selected" class="view-hint">{{ t('reports.viewInIframe') }}</p>
      <div v-if="selected" class="iframe-wrap">
        <iframe :src="selectedSrc" class="report-frame" :title="`report ${selected}`"></iframe>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page-title {
  font-size: var(--text-xl);
  margin-bottom: var(--sp-4);
}

.date-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--sp-3);
}

.date-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-1);
  padding: var(--sp-3);
  border-radius: var(--radius-card);
  border: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  color: var(--text-primary);
  transition:
    border-color 150ms ease-out,
    background 150ms ease-out;
}

.date-card:hover {
  border-color: var(--accent);
}

.date-card.active {
  border-color: var(--accent);
  background: var(--bg-raised);
}

.badge.latest {
  background: var(--sem-info);
  color: #fff;
  align-self: center;
}

.date-text {
  font-size: var(--text-base);
}

.meta {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.view-hint {
  margin: var(--sp-4) 0 var(--sp-2);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.iframe-wrap {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  overflow: hidden;
  background: #fff; /* 报告页为亮色排版（延续推送报告），暗色主题下保持原样渲染 */
}

.report-frame {
  display: block;
  width: 100%;
  height: 70vh;
  border: none;
}

.loading {
  padding: var(--sp-12);
  text-align: center;
  color: var(--text-secondary);
}
</style>
