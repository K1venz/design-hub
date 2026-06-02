import { useEffect } from 'react'
import { BrowserRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { toast } from 'sonner'

import { UNAUTHORIZED_EVENT } from '@/api/client'
import { queryClient } from '@/api/query-client'
import { AppLayout } from '@/components/layout/AppLayout'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AdminModelsPage } from '@/pages/AdminModelsPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { ForbiddenPage } from '@/pages/ForbiddenPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { WorkbenchPage } from '@/pages/WorkbenchPage'
import { ProtectedRoute } from '@/routes/ProtectedRoute'
import { RoleRoute } from '@/routes/RoleRoute'
import { ROLE_MANAGER } from '@/stores/auth-store'

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
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<WorkbenchPage />} />
          <Route
            path="dashboard"
            element={
              <RoleRoute allow={[ROLE_MANAGER]}>
                <DashboardPage />
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
