import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type Period = components['schemas']['Period']
export type Overview = components['schemas']['OverviewOut']
export type ModelCost = components['schemas']['ModelOut']
export type TierCost = components['schemas']['TierOut']
export type DesignerCost = components['schemas']['DesignerOut']
export type ProjectCost = components['schemas']['ProjectOut']

type Dim = components['schemas']['Dimension']

// 后端按 dim 返回不同形状（OpenAPI 表达为联合，无法据 query 判别）。
// 各维度按契约断言具体类型——后端保证该 dim 的响应形状。
async function fetchCost<T>(dim: Dim, period: Period): Promise<T> {
  const { data, error } = await api.GET('/dashboard/cost', {
    params: { query: { dim, period } },
  })
  if (error || data == null) throw new Error(errorMessage(error, '获取报表失败'))
  return data as T
}

const key = (dim: Dim, period: Period) => ['dashboard', dim, period] as const

export function useOverview(period: Period) {
  return useQuery({ queryKey: key('overview', period), queryFn: () => fetchCost<Overview>('overview', period) })
}
export function useModelCosts(period: Period) {
  return useQuery({ queryKey: key('model', period), queryFn: () => fetchCost<ModelCost[]>('model', period) })
}
export function useTierCosts(period: Period) {
  return useQuery({ queryKey: key('tier', period), queryFn: () => fetchCost<TierCost[]>('tier', period) })
}
export function useDesignerCosts(period: Period) {
  return useQuery({ queryKey: key('designer', period), queryFn: () => fetchCost<DesignerCost[]>('designer', period) })
}
export function useProjectCosts(period: Period) {
  return useQuery({ queryKey: key('project', period), queryFn: () => fetchCost<ProjectCost[]>('project', period) })
}
