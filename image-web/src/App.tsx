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
import { CustomersPage } from '@/pages/CustomersPage'
import { ForbiddenPage } from '@/pages/ForbiddenPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { HistoryDetailPage } from '@/pages/HistoryDetailPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { WorkbenchPage } from '@/pages/WorkbenchPage'
import { ProtectedRoute } from '@/routes/ProtectedRoute'
import { RoleRoute } from '@/routes/RoleRoute'
import { ROLE_MANAGER } from '@/stores/auth-store'

// recharts 体量较大，按路由懒加载切出独立 chunk
const DashboardPage = lazy(() =>
  import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
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
      <Route element={<ProtectedRoute />}>
        <Route element={<WorkbenchLayout />}>
          <Route index element={<WorkbenchPage />} />
        </Route>
        <Route element={<AppLayout />}>
          <Route path="history" element={<HistoryPage />} />
          <Route path="history/:jobId" element={<HistoryDetailPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route
            path="dashboard"
            element={
              <RoleRoute allow={[ROLE_MANAGER]}>
                <Suspense fallback={<FullPageLoader label="载入仪表盘…" />}>
                  <DashboardPage />
                </Suspense>
              </RoleRoute>
            }
          />
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
