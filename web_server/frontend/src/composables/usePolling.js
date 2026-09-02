/*
 * design/04 §4 usePolling：可见性感知的轮询
 * - 页面隐藏 clearInterval；恢复时立即 fetch 一次再重启（隐藏不清 data，只置 stale）
 * - 失败 ×2 退避：间隔翻倍，上限 60s；成功后恢复正常间隔
 */
import { onMounted, onUnmounted, ref } from 'vue'

const MAX_INTERVAL = 60000

export function usePolling(fn, intervalMs = 60000) {
  const stale = ref(false)
  let timer = null
  let failures = 0
  let stopped = false

  const currentInterval = () => Math.min(intervalMs * 2 ** failures, MAX_INTERVAL)

  async function tick() {
    try {
      await fn()
      failures = 0
      stale.value = false
    } catch {
      failures += 1
      stale.value = true
    }
  }

  function schedule() {
    clearTimeout(timer)
    timer = setTimeout(async () => {
      await tick()
      if (!stopped) schedule()
    }, currentInterval())
  }

  function start() {
    stopped = false
    schedule()
  }

  function stop() {
    stopped = true
    clearTimeout(timer)
  }

  async function onVisibilityChange() {
    if (document.hidden) {
      stop() // 隐藏：停轮询，不清数据（04 §4：只置 stale 语义保留给 UI）
    } else {
      await tick() // 恢复：立即刷一次再重启
      stale.value = false
      start()
    }
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', onVisibilityChange)
    start()
  })

  onUnmounted(() => {
    document.removeEventListener('visibilitychange', onVisibilityChange)
    stop()
  })

  return { stale, refresh: tick }
}
