import type { ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const PALETTE = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
]

/** 每个色板色一条竖向渐变（顶部淡、底部实），让柱子更有质感. */
function BarGradients() {
  return (
    <defs>
      {PALETTE.map((c, i) => (
        <linearGradient key={i} id={`bar-grad-${i}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity={0.62} />
          <stop offset="100%" stopColor={c} stopOpacity={1} />
        </linearGradient>
      ))}
    </defs>
  )
}

const AXIS_TICK = { fontSize: 12, fill: 'var(--muted-foreground)' }
const TOOLTIP_STYLE = {
  background: 'var(--popover)',
  border: '1px solid var(--border)',
  borderRadius: '0.5rem',
  fontSize: '12px',
}

function ChartFrame({ empty, children }: { empty: boolean; children: ReactNode }) {
  if (empty) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        当前周期暂无数据
      </div>
    )
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        {children as React.ReactElement}
      </ResponsiveContainer>
    </div>
  )
}

interface BarRow {
  label: string
  value: number
}

/** 单序列柱状图（按模型/设计师/项目的成本等）. */
export function CostBarChart({
  rows,
  unit = '¥',
}: {
  rows: BarRow[]
  unit?: string
}) {
  return (
    <ChartFrame empty={rows.length === 0}>
      <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
        <BarGradients />
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={48} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ fill: 'var(--muted)', opacity: 0.4 }}
          formatter={(v) => [`${unit}${Number(v).toFixed(2)}`, '成本']}
        />
        <Bar dataKey="value" radius={[6, 6, 0, 0]} maxBarSize={56}>
          {rows.map((_, i) => (
            <Cell key={i} fill={`url(#bar-grad-${i % PALETTE.length})`} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  )
}

interface TierRow {
  tier: string
  actual: number
  target: number
}

/** 档位实际占比 vs 目标占比（PRD 70-25-5 对照）. */
export function TierShareChart({ rows }: { rows: TierRow[] }) {
  return (
    <ChartFrame empty={rows.length === 0}>
      <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
        <BarGradients />
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="tier" tick={AXIS_TICK} tickLine={false} axisLine={false} />
        <YAxis
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={44}
          tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ fill: 'var(--muted)', opacity: 0.4 }}
          formatter={(v, name) => [`${Math.round(Number(v) * 100)}%`, String(name)]}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="actual" name="实际" fill="url(#bar-grad-0)" radius={[6, 6, 0, 0]} maxBarSize={40} />
        <Bar dataKey="target" name="目标" fill="url(#bar-grad-1)" radius={[6, 6, 0, 0]} maxBarSize={40} />
      </BarChart>
    </ChartFrame>
  )
}
