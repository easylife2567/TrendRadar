<script setup>
/*
 * ECharts 封装（design/04 §4 / 10 §2.3）
 * - props.option 驱动：watch option → setOption（数据更新不重播动画）
 * - 主题切换：MutationObserver 监听 html[data-theme] → dispose + 重新 init（10 §2.3）
 * - 容器尺寸：ResizeObserver 自适应
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { baseOptionTheme, echarts } from '../styles/charts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: Number, default: 260 },
})

const el = ref(null)
let chart = null
let resizeObserver = null
let themeObserver = null

function mergeTheme(userOption) {
  // 深合并太重：主题片段放最底层，用户 option 覆盖同名顶层键
  // （约定：页面 option 不写 color/textStyle 全局段，需要定制单轴时自行内联）
  const theme = baseOptionTheme()
  const merged = {
    animationDuration: 400, // 10 §7 图表动画：首载 400ms
    ...theme,
    ...userOption,
    legend: { ...theme.legend, ...(userOption.legend || {}) },
    tooltip: { ...theme.tooltip, ...(userOption.tooltip || {}) },
  }
  return merged
}

function render() {
  if (!el.value) return
  chart.setOption(mergeTheme(props.option), { notMerge: true, lazyUpdate: true })
}

onMounted(() => {
  chart = echarts.init(el.value)
  render()

  resizeObserver = new ResizeObserver(() => chart && chart.resize())
  resizeObserver.observe(el.value)

  // 主题切换 = dispose + 重新 init（不手维护两套色值）
  themeObserver = new MutationObserver(() => {
    if (!chart || !el.value) return
    chart.dispose()
    chart = echarts.init(el.value)
    render()
  })
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
})

watch(
  () => props.option,
  () => render(),
  { deep: true }
)

onUnmounted(() => {
  resizeObserver?.disconnect()
  themeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" :style="{ width: '100%', height: height + 'px' }"></div>
</template>
