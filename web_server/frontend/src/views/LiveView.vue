<script setup>
/*
 * 实时热榜 /live（design/04 §3.2，US-1/2）
 * 平台 tab + 分组/平铺视图 + 排名历史抽屉；60s 轮询
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import { useI18n } from '../composables/useI18n'
import { usePolling } from '../composables/usePolling'
import NewsItem from '../components/NewsItem.vue'
import PlatformTabs from '../components/PlatformTabs.vue'
import RankHistoryDrawer from '../components/RankHistoryDrawer.vue'
import EmptyState from '../components/EmptyState.vue'

const { t } = useI18n()

const loading = ref(true)
const items = ref([])
const selectedPlatform = ref('')
const viewMode = ref('grouped') // grouped | flat
const drawer = ref({ open: false, item: null })

const today = new Date().toISOString().slice(0, 10)

async function fetchData() {
  const data = await api.get(`/api/news/date/${today}?limit=300&include_url=true`)
  items.value = data || []
}

const { stale, refresh } = usePolling(fetchData, 60000)

onMounted(async () => {
  try {
    await fetchData()
  } catch {
    /* toast 已弹 */
  } finally {
    loading.value = false
  }
})

const platforms = computed(() => {
  const map = new Map()
  for (const it of items.value) {
    const cur = map.get(it.platform)
    if (cur) cur.count += 1
    else map.set(it.platform, { id: it.platform, name: it.platform_name || it.platform, count: 1 })
  }
  return [...map.values()]
})

const filtered = computed(() =>
  selectedPlatform.value ? items.value.filter((i) => i.platform === selectedPlatform.value) : items.value
)

const grouped = computed(() => {
  const byPlatform = new Map()
  for (const it of filtered.value) {
    if (!byPlatform.has(it.platform)) byPlatform.set(it.platform, { id: it.platform, name: it.platform_name, items: [] })
    byPlatform.get(it.platform).items.push(it)
  }
  return [...byPlatform.values()]
})

function openDrawer(item) {
  drawer.value = { open: true, item }
}
</script>

<template>
  <div class="page">
    <div class="head-row">
      <h1 class="page-title">{{ t('live.title') }}</h1>
      <span v-if="stale" class="stale-hint">{{ t('topbar.stale') }}</span>
      <div class="view-switch">
        <button
          class="btn btn-sm"
          :class="viewMode === 'grouped' ? 'btn-primary' : 'btn-secondary'"
          @click="viewMode = 'grouped'"
        >
          {{ t('live.grouped') }}
        </button>
        <button
          class="btn btn-sm"
          :class="viewMode === 'flat' ? 'btn-primary' : 'btn-secondary'"
          @click="viewMode = 'flat'"
        >
          {{ t('live.flat') }}
        </button>
      </div>
    </div>

    <PlatformTabs v-model="selectedPlatform" :platforms="platforms" :all-label="t('live.allPlatforms')" />

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>

    <EmptyState
      v-else-if="!items.length"
      :text="t('live.empty')"
      :hint="t('live.emptyHint')"
    />

    <template v-else>
      <!-- 分组视图 -->
      <section v-if="viewMode === 'grouped'" class="groups">
        <div v-for="g in grouped" :key="g.id" class="card group-card">
          <h2 class="group-name">
            {{ g.name }}
            <span class="mono-num count">{{ g.items.length }}</span>
          </h2>
          <NewsItem v-for="it in g.items" :key="g.id + it.title" :item="it" @open="openDrawer" />
        </div>
      </section>

      <!-- 平铺视图 -->
      <div v-else class="card">
        <NewsItem v-for="it in filtered" :key="it.platform + it.title" :item="it" @open="openDrawer" />
      </div>
    </template>

    <RankHistoryDrawer
      :open="drawer.open"
      :item="drawer.item"
      :date="today"
      @close="drawer.open = false"
    />
  </div>
</template>

<style scoped>
.head-row {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  margin-bottom: var(--sp-4);
  flex-wrap: wrap;
}

.page-title {
  font-size: var(--text-xl);
}

.stale-hint {
  font-size: var(--text-xs);
  color: var(--sem-warn);
}

.view-switch {
  margin-left: auto;
  display: flex;
  gap: var(--sp-2);
}

.groups {
  margin-top: var(--sp-4);
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: var(--sp-4);
  align-items: start;
}

.group-card {
  padding: var(--sp-3);
}

.group-name {
  font-size: var(--text-base);
  margin-bottom: var(--sp-2);
}

.count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-left: var(--sp-2);
}

.card {
  margin-top: var(--sp-4);
  padding: var(--sp-2) 0;
}

.loading {
  padding: var(--sp-12);
  text-align: center;
  color: var(--text-secondary);
}
</style>
