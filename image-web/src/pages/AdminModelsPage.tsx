import { SlidersHorizontalIcon } from 'lucide-react'

import { PagePlaceholder } from '@/components/PagePlaceholder'

export function AdminModelsPage() {
  return (
    <PagePlaceholder
      icon={SlidersHorizontalIcon}
      title="模型配置"
      description="ModelConfig 热更：启停模型、调单价（注入 Provider）。仅管理者可见。"
      endpoints={['GET /admin/models', 'PUT /admin/models/{name}']}
      pkg="FE-7"
    />
  )
}
