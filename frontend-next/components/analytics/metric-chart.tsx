"use client"

import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils/cn"

interface DataPoint {
  name: string
  [key: string]: string | number
}

interface MetricChartProps {
  title: string
  data: DataPoint[]
  type?: "line" | "bar" | "area"
  dataKey?: string
  color?: string
  height?: number
  className?: string
  showGrid?: boolean
  formatY?: (value: number) => string
}

export function MetricChart({
  title,
  data,
  type = "line",
  dataKey = "value",
  color = "var(--color-primary)",
  height = 250,
  className,
  showGrid = true,
  formatY,
}: MetricChartProps) {
  const ChartComponent = type === "bar" ? BarChart : type === "area" ? AreaChart : LineChart

  const tooltipStyle = {
    contentStyle: {
      background: "hsl(0, 0%, 7%)",
      border: "1px solid hsl(240, 4%, 16%)",
      borderRadius: "8px",
      fontSize: "12px",
    },
    labelStyle: { color: "hsl(0, 0%, 65%)" },
  }

  return (
    <Card className={cn("", className)}>
      <CardHeader>
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div style={{ width: "100%", height }}>
          <ResponsiveContainer>
            <ChartComponent data={data}>
              {showGrid && (
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="hsl(240, 4%, 16%)"
                  vertical={false}
                />
              )}
              <XAxis
                dataKey="name"
                tick={{ fontSize: 11, fill: "hsl(240, 4%, 65%)" }}
                axisLine={{ stroke: "hsl(240, 4%, 16%)" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "hsl(240, 4%, 65%)" }}
                axisLine={false}
                tickLine={false}
                tickFormatter={formatY}
              />
              <Tooltip
                contentStyle={tooltipStyle.contentStyle}
                labelStyle={tooltipStyle.labelStyle}
              />
              {type === "bar" ? (
                <Bar
                  dataKey={dataKey}
                  fill={color}
                  fillOpacity={0.8}
                  radius={[4, 4, 0, 0]}
                />
              ) : type === "area" ? (
                <Area
                  type="monotone"
                  dataKey={dataKey}
                  stroke={color}
                  fill={color}
                  fillOpacity={0.1}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, fill: color }}
                />
              ) : (
                <Line
                  type="monotone"
                  dataKey={dataKey}
                  stroke={color}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, fill: color }}
                />
              )}
            </ChartComponent>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
