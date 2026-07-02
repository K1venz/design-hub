import { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { toast } from 'sonner'

import { UNAUTHORIZED_EVENT } from '@/api/client'
import { queryClient } from '@/api/query-client'
import { FullPageLoader } from '@/components/feedback/FullPageLoader'
import { AppLayout } from '@/components/layout/AppLayout'
import { WorkbenchLayout } from '@/components/layout/WorkbenchLayout'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AdminModelsPage } from '@/pages/AdminModelsPage'
import { AdminUsersPage } from '@/pages/AdminUsersPage'
import { ChatPage } from '@/pages/ChatPage'
import { CloneWorkbenchPage } from '@/pages/CloneWorkbenchPage'
import { EditWorkbenchPage } from '@/pages/EditWorkbenchPage'
import { ForbiddenPage } from '@/pages/ForbiddenPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { HistoryDetailPage } from '@/pages/HistoryDetailPage'
import { HomePage } from '@/pages/HomePage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { TermsPage } from '@/pages/legal/TermsPage'
import { PrivacyPage } from '@/pages/legal/PrivacyPage'
import { WorkbenchPage } from '@/pages/WorkbenchPage'
import { ProtectedRoute } from '@/routes/ProtectedRoute'
import { RoleRoute } from '@/routes/RoleRoute'
import { ROLE_MANAGER } from '@/stores/auth-store'

// UI 风格预览（throwaway 选型用，第二轮 Western AI-product）：仅 DEV 注册路由。
// import() 必须在 DEV 分支内（静态可消除），否则 chunk 仍会被产出进 prod dist。
const devLazy = (load: () => Promise<{ default: React.ComponentType }>) =>
  import.meta.env.DEV ? lazy(load) : () => null
const StylePreviewIndex = devLazy(() =>
  import('@/pages/style-preview/StylePreviewIndex').then((m) => ({ default: m.StylePreviewIndex })),
)
const LinearPreview = devLazy(() =>
  import('@/pages/style-preview/LinearPreview').then((m) => ({ default: m.LinearPreview })),
)
const GeistPreview = devLazy(() =>
  import('@/pages/style-preview/GeistPreview').then((m) => ({ default: m.GeistPreview })),
)
const ClaudePreview = devLazy(() =>
  import('@/pages/style-preview/ClaudePreview').then((m) => ({ default: m.ClaudePreview })),
)
const GlassPreview = devLazy(() =>
  import('@/pages/style-preview/GlassPreview').then((m) => ({ default: m.GlassPreview })),
)

/** 监听 401 广播：提示并跳登录（会话已被中间件清空）. */
function UnauthorizedWatcher() {
  const navigate = useNavigate()
  useEffect(() => {
    function onUnauthorized() {
      toast.error('登录已过期，请重新登录')
      navigate('/login', { replace: true })
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [navigate])
  return null
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* 公开落地页（未登录可浏览，页面自带 AppShell）：首页 + 协议页 */}
      <Route index element={<HomePage />} />
      <Route path="/terms" element={<TermsPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />

      <Route element={<ProtectedRoute />}>
        {/* 帮我设计（登录内测，自带 AppShell） */}
        <Route path="chat" element={<ChatPage />} />
        <Route element={<WorkbenchLayout />}>
          <Route path="set" element={<WorkbenchPage />} />
          <Route path="clone" element={<CloneWorkbenchPage />} />
          <Route path="edit/:jobId/:imageKey" element={<EditWorkbenchPage />} />
        </Route>
        <Route element={<AppLayout />}>
          <Route path="history" element={<HistoryPage />} />
          <Route path="history/:jobId" element={<HistoryDetailPage />} />
          <Route
            path="admin/models"
            element={
              <RoleRoute allow={[ROLE_MANAGER]}>
                <AdminModelsPage />
              </RoleRoute>
            }
          />
          <Route
            path="admin/users"
            element={
              <RoleRoute allow={[ROLE_MANAGER]}>
                <AdminUsersPage />
              </RoleRoute>
            }
          />
        </Route>
      </Route>
      {import.meta.env.DEV && (
        <Route path="/style-preview">
          <Route
            index
            element={
              <Suspense fallback={<FullPageLoader label="载入预览…" />}>
                <StylePreviewIndex />
              </Suspense>
            }
          />
          {(
            [
              ['linear', LinearPreview],
              ['geist', GeistPreview],
              ['claude', ClaudePreview],
              ['glass', GlassPreview],
            ] as const
          ).map(([id, Comp]) => (
            <Route
              key={id}
              path={id}
              element={
                <Suspense fallback={<FullPageLoader label="载入预览…" />}>
                  <Comp />
                </Suspense>
              }
            />
          ))}
        </Route>
      )}
      <Route path="/403" element={<ForbiddenPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>
        <BrowserRouter>
          <UnauthorizedWatcher />
          <AppRoutes />
        </BrowserRouter>
        <Toaster position="top-center" />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
