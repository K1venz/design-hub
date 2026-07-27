import type { ReactNode } from 'react'

import { AppTopBar } from '@/components/layout/AppTopBar'

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="canvas-blobs flex h-svh flex-col bg-background text-wb-ink-1">
      <AppTopBar />
      {children}
    </div>
  )
}
