import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type Customer = components['schemas']['CustomerOut']
export type CustomerCreate = components['schemas']['CustomerCreate']

export const customerKeys = {
  all: ['customers'] as const,
  detail: (id: number) => ['customers', id] as const,
}

export function useCustomers() {
  return useQuery({
    queryKey: customerKeys.all,
    queryFn: async (): Promise<Customer[]> => {
      const { data, error } = await api.GET('/customers')
      if (error || !data) throw new Error(errorMessage(error, '获取客户列表失败'))
      return data
    },
  })
}

export function useCustomer(id: number | undefined) {
  return useQuery({
    queryKey: id == null ? ['customers', 'nil'] : customerKeys.detail(id),
    enabled: id != null,
    queryFn: async (): Promise<Customer> => {
      const { data, error } = await api.GET('/customers/{customer_id}', {
        params: { path: { customer_id: id as number } },
      })
      if (error || !data) throw new Error(errorMessage(error, '获取客户失败'))
      return data
    },
  })
}

export function useCreateCustomer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: CustomerCreate): Promise<Customer> => {
      const { data, error } = await api.POST('/customers', { body })
      if (error || !data) throw new Error(errorMessage(error, '创建客户失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: customerKeys.all }),
  })
}
