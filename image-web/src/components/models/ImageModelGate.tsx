import type { ReactNode } from 'react'

import { useImageModels } from '@/api/models'
import { ImageModelContext } from '@/components/models/image-model-context'
import { useModelSelection } from '@/components/models/use-model-selection'

export function ImageModelGate({ children }: { children: ReactNode }) {
  const query = useImageModels()
  const value = useModelSelection('image', query)

  return (
    <ImageModelContext.Provider value={value}>
      {children}
    </ImageModelContext.Provider>
  )
}
