import type { ReactNode } from 'react'

import { AmbientBackground } from '@/components/layout/AmbientBackground'
import { AppTopBar } from '@/components/layout/AppTopBar'

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative h-svh overflow-hidden bg-background text-wb-ink-1">
      <AmbientBackground />
      <div className="relative z-10 flex min-h-0 flex-1 flex-col h-full">
        <AppTopBar />
        {children}
      </div>
    </div>
  )
}
