/*
 * design/04 §4 useDateRange：range 快捷词集合
 * 与后端 DateParser RANGE_EXPRESSIONS 对齐（design/07 偏差⑤：
 * 支持「最近7天/近7天/上周/last 7 days」式表达，不支持 last7d 连写）
 * MVP：前端直接把表达式传给 API 的 range 参数，由服务端解析
 */
import { computed, ref } from 'vue'
import { useI18n } from './useI18n'

export function useDateRange(initial = '最近7天') {
  const { t } = useI18n()
  const range = ref(initial)

  // 快捷词（value 即 API 的 range 参数）
  const presets = computed(() => [
    { label: t('range.today'), value: '今天' },
    { label: t('range.yesterday'), value: '昨天' },
    { label: t('range.last7'), value: '最近7天' },
    { label: t('range.last30'), value: '最近30天' },
    { label: t('range.lastWeek'), value: '上周' },
    { label: t('range.thisWeek'), value: '本周' },
    { label: t('range.lastMonth'), value: '上月' },
    { label: t('range.thisMonth'), value: '本月' },
  ])

  return { range, presets }
}
