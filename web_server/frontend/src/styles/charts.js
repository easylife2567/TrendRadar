/*
 * design/10 §2.3：ECharts 按需引入 + 主题从 tokens 生成
 * 主题切换 = dispose + 重新 init（在 TrendChart.vue 内实现），色值不手维护两套
 *
 * 首屏预算（04 §6：gzip < 200KB）：P2 只注册 Line/Bar——PieChart、DataZoom、
 * MarkLine 在 P3（情感环形图、生命周期标注）落地时按需加回，避免无谓的首屏体积
 */
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

/** 分类色板（10 §2.3：8 色暗底校准） */
export const CHART_PALETTE = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  'var(--chart-6)',
  'var(--chart-7)',
  'var(--chart-8)',
]

/** 从当前 tokens 读出 ECharts 主题片段（getComputedStyle，不手维护色值） */
export function readTokenTheme() {
  const s = getComputedStyle(document.documentElement)
  const v = (name) => s.getPropertyValue(name).trim()
  return {
    textColor: v('--text-secondary'),
    subTextColor: v('--text-muted'),
    borderColor: v('--border-subtle'),
    axisLine: v('--border-subtle'),
    splitLine: v('--border-subtle'),
    tooltipBg: v('--bg-raised'),
    seriesColor(vRef) {
      return v(vRef)
    },
    palette: CHART_PALETTE.map((ref) => v(ref.replace('var(', '').replace(')', ''))),
  }
}

/** 通用 option 片段：轴线/网格/tooltip 用 token 色 */
export function baseOptionTheme() {
  const t = readTokenTheme()
  return {
    color: t.palette,
    textStyle: { color: t.textColor },
    axisPointer: { lineStyle: { color: t.axisLine } },
    grid: { left: 48, right: 16, top: 32, bottom: 28, containLabel: true },
    categoryAxis: {
      axisLine: { lineStyle: { color: t.axisLine } },
      axisTick: { show: false },
      axisLabel: { color: t.textColor, fontSize: 11 },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisLabel: { color: t.textColor, fontSize: 11 },
      splitLine: { lineStyle: { color: t.splitLine } },
    },
    legend: { textStyle: { color: t.textColor, fontSize: 11 }, itemWidth: 14, itemHeight: 8 },
    tooltip: {
      backgroundColor: t.tooltipBg,
      borderColor: t.borderColor,
      textStyle: { color: t.textColor, fontSize: 12 },
    },
  }
}

export { echarts }
