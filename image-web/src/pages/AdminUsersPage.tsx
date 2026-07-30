import { useState } from 'react'
import { BanIcon, RotateCcwIcon } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import {
  useSetRole,
  useSetUserStatus,
  useUsers,
  type AdminUser,
} from '@/api/users'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { yuan } from '@/lib/format'
import {
  ROLE_DESIGNER,
  ROLE_MANAGER,
  roleLabel,
  useCurrentUser,
  type Role,
} from '@/stores/auth-store'

const LIMIT = 20
const number = new Intl.NumberFormat('zh-CN')

function dateTime(value: string | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function StatusDialog({
  user,
  protectedAccount,
}: {
  user: AdminUser
  protectedAccount: boolean
}) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const setStatus = useSetUserStatus()
  const disabling = user.enabled

  async function submit() {
    const trimmedReason = reason.trim()
    if (disabling && !trimmedReason) {
      toast.error('请填写停用原因')
      return
    }
    try {
      await setStatus.mutateAsync({
        id: user.user_id,
        enabled: !disabling,
        reason: disabling ? trimmedReason : '',
      })
      toast.success(`「${user.name}」已${disabling ? '停用' : '恢复'}`)
      setOpen(false)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : '更新用户状态失败',
      )
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next) setReason('')
      }}
    >
      <DialogTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant={disabling ? 'destructive' : 'outline'}
          disabled={protectedAccount}
          title={
            protectedAccount
              ? '不能停用当前账号或最后一名启用中的管理者'
              : undefined
          }
        >
          {disabling ? (
            <BanIcon className="size-3.5" />
          ) : (
            <RotateCcwIcon className="size-3.5" />
          )}
          {disabling ? '停用' : '恢复'}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {disabling ? '停用这个账号？' : '恢复这个账号？'}
          </DialogTitle>
          <DialogDescription>
            {disabling
              ? '停用后，该用户的现有会话和后续 API 请求都会被拒绝。'
              : '恢复后，该用户可以重新登录并使用平台功能。'}
          </DialogDescription>
        </DialogHeader>
        {disabling ? (
          <div className="space-y-2">
            <Label htmlFor={`disable-reason-${user.user_id}`}>
              停用原因
            </Label>
            <Textarea
              id={`disable-reason-${user.user_id}`}
              value={reason}
              maxLength={500}
              placeholder="仅管理员可见"
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
        ) : null}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen(false)}
          >
            取消
          </Button>
          <Button
            type="button"
            variant={disabling ? 'destructive' : 'default'}
            disabled={setStatus.isPending}
            onClick={() => void submit()}
          >
            {setStatus.isPending
              ? '处理中…'
              : disabling
                ? '确认停用'
                : '确认恢复'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function AdminUsersPage() {
  const me = useCurrentUser()
  const [searchParams, setSearchParams] = useSearchParams()
  const setRole = useSetRole()
  const roleParam = searchParams.get('role')
  const enabledParam = searchParams.get('enabled')
  const offsetParam = Number(searchParams.get('offset') ?? 0)
  const offset =
    Number.isInteger(offsetParam) && offsetParam >= 0 ? offsetParam : 0

  function setParam(key: string, value?: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set(key, value)
      else next.delete(key)
      if (key !== 'offset') next.delete('offset')
      return next
    })
  }

  const users = useUsers({
    q: searchParams.get('q') || undefined,
    role:
      roleParam === ROLE_MANAGER || roleParam === ROLE_DESIGNER
        ? roleParam
        : undefined,
    enabled:
      enabledParam === 'true'
        ? true
        : enabledParam === 'false'
          ? false
          : undefined,
    limit: LIMIT,
    offset,
  })
  const activeManagers = useUsers({
    role: ROLE_MANAGER,
    enabled: true,
    limit: 1,
    offset: 0,
  })

  async function changeRole(user: AdminUser, role: Role) {
    if (role === user.role) return
    try {
      await setRole.mutateAsync({ id: user.user_id, role })
      toast.success(`「${user.name}」已设为${roleLabel(role)}`)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : '更新角色失败',
      )
    }
  }

  return (
    <div className="space-y-4">
      <header className="px-1">
        <h1 className="text-2xl font-semibold tracking-tight text-wb-ink-1">
          用户管理
        </h1>
        <p className="mt-1 text-xs text-wb-ink-6">
          管理账号角色与可用状态，并查看每位用户的实际平台用量。
        </p>
      </header>

      <Card className="grid gap-3 border-white/80 bg-white/82 p-3 sm:grid-cols-3">
        <Input
          placeholder="搜索姓名或邮箱"
          value={searchParams.get('q') ?? ''}
          onChange={(event) =>
            setParam('q', event.target.value.trim())
          }
        />
        <Select
          value={roleParam ?? 'all'}
          onValueChange={(value) =>
            setParam('role', value === 'all' ? undefined : value)
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="角色" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部角色</SelectItem>
            <SelectItem value={ROLE_DESIGNER}>用户</SelectItem>
            <SelectItem value={ROLE_MANAGER}>管理者</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={enabledParam ?? 'all'}
          onValueChange={(value) =>
            setParam(
              'enabled',
              value === 'all' ? undefined : value,
            )
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="账号状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="true">启用</SelectItem>
            <SelectItem value="false">已停用</SelectItem>
          </SelectContent>
        </Select>
      </Card>

      <Card className="overflow-hidden border-white/80 bg-white/82 p-0">
        {users.isLoading || activeManagers.isLoading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 6 }, (_, index) => (
              <Skeleton key={index} className="h-12 w-full" />
            ))}
          </div>
        ) : users.isError || activeManagers.isError ? (
          <div className="py-16 text-center text-sm text-wb-red">
            用户列表加载失败，请稍后重试。
          </div>
        ) : users.data?.items.length ? (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>用户</TableHead>
                    <TableHead>角色</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>出图 / 图片</TableHead>
                    <TableHead>图片调用</TableHead>
                    <TableHead>Chat 调用 / Token</TableHead>
                    <TableHead>平台成本</TableHead>
                    <TableHead>最近活跃</TableHead>
                    <TableHead className="text-right">账号操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.data.items.map((user) => {
                    const self = String(user.user_id) === me.user_id
                    const lastActiveManager =
                      user.role === ROLE_MANAGER &&
                      user.enabled &&
                      activeManagers.data?.total === 1
                    const protectedAccount =
                      self || lastActiveManager
                    return (
                      <TableRow key={user.user_id}>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div>
                              <p className="font-medium text-wb-ink-2">
                                {user.name}
                              </p>
                              <p className="text-xs text-wb-ink-6">
                                {user.email}
                              </p>
                            </div>
                            {self ? (
                              <Badge
                                variant="secondary"
                                className="text-[10px]"
                              >
                                你
                              </Badge>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Select
                            value={user.role}
                            disabled={
                              setRole.isPending || protectedAccount
                            }
                            onValueChange={(value) =>
                              void changeRole(user, value as Role)
                            }
                          >
                            <SelectTrigger
                              size="sm"
                              className="w-24"
                              title={
                                protectedAccount
                                  ? '不能降级当前账号或最后一名启用中的管理者'
                                  : undefined
                              }
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={ROLE_DESIGNER}>
                                用户
                              </SelectItem>
                              <SelectItem value={ROLE_MANAGER}>
                                管理者
                              </SelectItem>
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              user.enabled ? 'outline' : 'destructive'
                            }
                          >
                            {user.enabled ? '启用' : '已停用'}
                          </Badge>
                        </TableCell>
                        <TableCell className="tabular">
                          {number.format(user.jobs)} /{' '}
                          {number.format(user.successful_images)}
                        </TableCell>
                        <TableCell className="tabular">
                          {number.format(user.image_calls)}
                        </TableCell>
                        <TableCell className="tabular">
                          {number.format(user.chat_calls)} /{' '}
                          {number.format(user.chat_total_tokens)}
                        </TableCell>
                        <TableCell className="tabular">
                          {yuan(user.platform_cost)}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-wb-ink-6">
                          {dateTime(user.last_activity_at)}
                        </TableCell>
                        <TableCell className="text-right">
                          <StatusDialog
                            user={user}
                            protectedAccount={
                              user.enabled && protectedAccount
                            }
                          />
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
            <AdminPagination
              total={users.data.total}
              limit={users.data.limit}
              offset={users.data.offset}
              onOffsetChange={(nextOffset) =>
                setParam('offset', String(nextOffset))
              }
            />
          </>
        ) : (
          <div className="py-16 text-center text-sm text-wb-ink-6">
            当前筛选下没有用户
          </div>
        )}
      </Card>
    </div>
  )
}
