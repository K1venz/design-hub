import { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { toast } from 'sonner'

import { useMe } from '@/api/auth'
import { UNAUTHORIZED_EVENT } from '@/api/client'
import { queryClient } from '@/api/query-client'
import { AdminLayout } from '@/components/admin/AdminLayout'
import { FullPageLoader } from '@/components/feedback/FullPageLoader'
import { AppLayout } from '@/components/layout/AppLayout'
import { WorkbenchLayout } from '@/components/layout/WorkbenchLayout'
import { ImageModelGate } from '@/components/models/ImageModelGate'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AdminModelsPage } from '@/pages/AdminModelsPage'
import { AdminOverviewPage } from '@/pages/AdminOverviewPage'
import { AdminRuntimeLogsPage } from '@/pages/AdminRuntimeLogsPage'
import { AdminUsersPage } from '@/pages/AdminUsersPage'
import { AdminAuditPage } from '@/pages/AdminAuditPage'
import { AdminGenerationDetailPage } from '@/pages/AdminGenerationDetailPage'
import { AdminGenerationsPage } from '@/pages/AdminGenerationsPage'
import { AdminUsagePage } from '@/pages/AdminUsagePage'
import { BackgroundWorkbenchPage } from '@/pages/BackgroundWorkbenchPage'
import { ChatPage } from '@/pages/ChatPage'
import { CloneWorkbenchPage } from '@/pages/CloneWorkbenchPage'
import { EditWorkbenchPage } from '@/pages/EditWorkbenchPage'
import { ForbiddenPage } from '@/pages/ForbiddenPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { HeroPage } from '@/pages/HeroPage'
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
import { AUTH_STORAGE_KEY, ROLE_MANAGER, useAuthStore } from '@/stores/auth-store'

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
const ModelSelectorDemoPage = devLazy(() =>
  import('@/pages/model-selector-demo/ModelSelectorDemoPage').then((module) => ({
    default: module.ModelSelectorDemoPage,
  })),
)

/**
 * 应用级用户水合：有 token 但 user 未载入时拉 /me 填 store。
 * 修「登录后回到公开页（首页等），顶栏仍显示登录/注册、要切进墙内页才更新」——
 * 此前 /me 只在 ProtectedRoute 里拉，公开页没人水合 user。与 ProtectedRoute 共用
 * 同一 ['me'] 查询（react-query 去重，不双发）；失败在公开页 fail-soft（401 由
 * client 中间件统一清会话广播，其余瞬时错不打扰浏览）。
 */
function AuthHydrator() {
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const { data } = useMe(Boolean(token) && !user)
  useEffect(() => {
    if (data) setUser(data)
  }, [data, setUser])
  return null
}

/** 监听 401 广播：提示并跳登录（会话已被中间件清空）. */
/** 未登录也可浏览的路径：401 只静默清会话（顶栏回未登录态），不弹窗不赶去登录页。 */
const PUBLIC_PATHS = new Set(['/', '/home', '/terms', '/privacy', '/login', '/register'])

function UnauthorizedWatcher() {
  const navigate = useNavigate()
  useEffect(() => {
    function onUnauthorized() {
      // 公开页带过期 token（AuthHydrator 水合 401）：会话已被 client 中间件清空，
      // 静默降级为未登录浏览即可；仅墙内页才提示+跳登录。
      if (PUBLIC_PATHS.has(window.location.pathname)) return
      toast.error('登录已过期，请重新登录')
      navigate('/login', { replace: true })
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [navigate])
  return null
}

/**
 * 多标签页登出同步（ISSUE-0058 §三.1）：监听 storage 事件——另一标签清 auth 键（登出）→
 * 本页也清会话并跳登录。仅 localStorage 模式生效（sessionStorage 无跨页事件；记住我=默认勾覆盖主流）。
 * 只广播登出方向：新值无 token 且本页仍有 token → 登出；登录/续期方向（有 token）不动。
 */
function MultiTabLogoutWatcher() {
  const navigate = useNavigate()
  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key !== AUTH_STORAGE_KEY) return
      let nextToken: unknown
      try {
        nextToken = e.newValue ? (JSON.parse(e.newValue) as { state?: { token?: unknown } })?.state?.token : null
      } catch {
        nextToken = null
      }
      if (!nextToken && useAuthStore.getState().token) {
        useAuthStore.getState().clear()
        queryClient.clear()
        if (!PUBLIC_PATHS.has(window.location.pathname)) navigate('/login', { replace: true })
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [navigate])
  return null
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* 公开落地页（未登录可浏览）：`/`=品牌 Hero 独立页；`/home`=项目首页（自带 AppShell）+ 协议页 */}
      <Route index element={<HeroPage />} />
      <Route path="/home" element={<HomePage />} />
      <Route path="/terms" element={<TermsPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />

      <Route element={<ProtectedRoute />}>
        {/* 帮我设计（登录内测，自带 AppShell） */}
        <Route
          path="chat"
          element={
            <ImageModelGate>
              <ChatPage />
            </ImageModelGate>
          }
        />
        <Route
          element={
            <ImageModelGate>
              <WorkbenchLayout />
            </ImageModelGate>
          }
        >
          <Route path="set" element={<WorkbenchPage />} />
          <Route path="clone" element={<CloneWorkbenchPage />} />
          <Route path="background" element={<BackgroundWorkbenchPage />} />
          <Route path="edit/:jobId/:imageKey" element={<EditWorkbenchPage />} />
        </Route>
        <Route element={<AppLayout />}>
          <Route path="history" element={<HistoryPage />} />
          <Route path="history/:jobId" element={<HistoryDetailPage />} />
        </Route>
        <Route
          path="admin"
          element={
            <RoleRoute allow={[ROLE_MANAGER]}>
              <AdminLayout />
            </RoleRoute>
          }
        >
          <Route index element={<AdminOverviewPage />} />
          <Route path="users" element={<AdminUsersPage />} />
          <Route path="generations" element={<AdminGenerationsPage />} />
          <Route
            path="generations/:jobId"
            element={<AdminGenerationDetailPage />}
          />
          <Route path="usage" element={<AdminUsagePage />} />
          <Route path="models" element={<AdminModelsPage />} />
          <Route path="audit" element={<AdminAuditPage />} />
          <Route path="logs" element={<AdminRuntimeLogsPage />} />
        </Route>
      </Route>
      {import.meta.env.DEV && (
        <Route
          path="/model-selector-demo"
          element={
            <Suspense fallback={<FullPageLoader label="载入模型选择器演示…" />}>
              <ModelSelectorDemoPage />
            </Suspense>
          }
        />
      )}
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
          <AuthHydrator />
          <UnauthorizedWatcher />
          <MultiTabLogoutWatcher />
          <AppRoutes />
        </BrowserRouter>
        <Toaster position="top-center" />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
