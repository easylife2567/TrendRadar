/*
 * design/04 §5：字典模式 i18n（zh-CN 默认 / en 对照）
 * 模块级 reactive 单例（无 Pinia，04 §4 状态两块原则）
 */
import { computed, reactive } from 'vue'
import zhCN from '../locales/zh-CN.json'
import en from '../locales/en.json'

const DICTS = { 'zh-CN': zhCN, en }
const STORAGE_KEY = 'trendradar_locale'

const state = reactive({
  locale: localStorage.getItem(STORAGE_KEY) || (navigator.language?.startsWith('zh') ? 'zh-CN' : 'en'),
})

function interpolate(template, params) {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, k) => (params[k] !== undefined ? String(params[k]) : `{${k}}`))
}

export function useI18n() {
  const t = (key, params) => {
    const dict = DICTS[state.locale] || DICTS['zh-CN']
    const val = key.split('.').reduce((acc, k) => (acc == null ? undefined : acc[k]), dict)
    const fallback = key.split('.').reduce((acc, k) => (acc == null ? undefined : acc[k]), DICTS['zh-CN'])
    const template = val !== undefined ? val : fallback !== undefined ? fallback : key
    return interpolate(template, params)
  }

  const setLocale = (locale) => {
    if (!DICTS[locale]) return
    state.locale = locale
    localStorage.setItem(STORAGE_KEY, locale)
    document.documentElement.lang = locale === 'zh-CN' ? 'zh-CN' : 'en'
  }

  return { t, locale: computed(() => state.locale), setLocale }
}
