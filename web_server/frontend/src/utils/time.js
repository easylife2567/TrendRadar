/*
 * 时间工具：相对时间（10 §9 AI 时间戳要求）与库内 "HH-MM" 短格式转换
 */
import { useI18n } from '../composables/useI18n'

export function fmtRelTime(input) {
  const { t } = useI18n()
  if (!input) return ''
  let ms
  if (typeof input === 'number') {
    ms = input < 1e12 ? input * 1000 : input
  } else {
    ms = new Date(String(input).replace(' ', 'T')).getTime()
    if (Number.isNaN(ms)) return String(input)
  }
  const diff = Date.now() - ms
  const min = Math.floor(diff / 60000)
  if (min < 1) return t('time.justNow')
  if (min < 60) return t('time.minutesAgo', { n: min })
  const hours = Math.floor(min / 60)
  if (hours < 24) return t('time.hoursAgo', { n: hours })
  return t('time.daysAgo', { n: Math.floor(hours / 24) })
}

/** 绝对时间（hover title 用，10 §9：相对时间 hover 显绝对时间） */
export function fmtAbsTime(input) {
  if (!input) return ''
  const ms =
    typeof input === 'number' ? (input < 1e12 ? input * 1000 : input) : new Date(String(input).replace(' ', 'T')).getTime()
  if (Number.isNaN(ms)) return String(input)
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/** 库内 crawl_time 短格式 "HH-MM"（爬取时间冒号被用作文件名分隔，存储为连字符） */
export function hhmm(v) {
  return typeof v === 'string' ? v.replace('-', ':') : v
}
