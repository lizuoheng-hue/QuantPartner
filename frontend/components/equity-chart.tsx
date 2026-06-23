"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import type { SeriesPoint } from "@/lib/types";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

interface EquityChartProps {
  strategy: SeriesPoint[];
  benchmark: SeriesPoint[];
  drawdown: SeriesPoint[];
}

export function EquityChart({ strategy, benchmark, drawdown }: EquityChartProps) {
  const option = useMemo(() => ({
    backgroundColor: "transparent",
    animationDuration: 500,
    tooltip: { trigger: "axis", backgroundColor: "#111923", borderColor: "#334155", textStyle: { color: "#e6edf3" } },
    legend: { top: 6, left: 12, textStyle: { color: "#8b9aab", fontSize: 11 }, data: ["策略净值", "沪深300"] },
    grid: [
      { left: 54, right: 20, top: 46, height: "55%" },
      { left: 54, right: 20, top: "76%", height: "14%" },
    ],
    xAxis: [
      { type: "category", data: strategy.map(item => item.date), boundaryGap: false, axisLine: { lineStyle: { color: "#263444" } }, axisLabel: { color: "#718096", hideOverlap: true } },
      { type: "category", gridIndex: 1, data: drawdown.map(item => item.date), boundaryGap: false, axisLine: { lineStyle: { color: "#263444" } }, axisLabel: { show: false } },
    ],
    yAxis: [
      { type: "value", scale: true, splitLine: { lineStyle: { color: "#1b2733" } }, axisLabel: { color: "#718096" } },
      { type: "value", gridIndex: 1, max: 0, splitLine: { lineStyle: { color: "#1b2733" } }, axisLabel: { color: "#718096", formatter: (value: number) => `${(value * 100).toFixed(0)}%` } },
    ],
    series: [
      { name: "策略净值", type: "line", showSymbol: false, smooth: false, data: strategy.map(item => item.value), lineStyle: { color: "#2388ff", width: 2 }, areaStyle: { color: "rgba(35,136,255,.07)" } },
      { name: "沪深300", type: "line", showSymbol: false, data: benchmark.map(item => item.value), lineStyle: { color: "#748193", width: 1.3 } },
      { name: "回撤", type: "line", xAxisIndex: 1, yAxisIndex: 1, showSymbol: false, data: drawdown.map(item => item.value), lineStyle: { color: "#2388ff", width: 1 }, areaStyle: { color: "rgba(35,136,255,.22)" } },
    ],
  }), [strategy, benchmark, drawdown]);

  return <ReactECharts option={option} style={{ height: 450, width: "100%" }} notMerge lazyUpdate />;
}
