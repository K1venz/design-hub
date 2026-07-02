import { toast } from 'sonner'

import { useSetRole, useUsers, type AppUser } from '@/api/users'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
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
import { ROLE_DESIGNER, ROLE_MANAGER, roleLabel, useCurrentUser, type Role } from '@/stores/auth-store'

export function AdminUsersPage() {
  const me = useCurrentUser()
  const users = useUsers()
  const setRole = useSetRole()

  async function changeRole(u: AppUser, role: Role) {
    if (role === u.role) return
    try {
      await setRole.mutateAsync({ id: u.id, role })
      toast.success(`「${u.name}」已设为${role}`)
    } catch (e) {
      // 如"最后一个管理者不可降级"→ 后端 409
      toast.error(e instanceof Error ? e.message : '更新角色失败')
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">用户管理</h2>
        <p className="text-sm text-muted-foreground">分配角色：用户 / 管理者。仅管理者可见。</p>
      </div>

      <Card className="overflow-hidden p-0">
        {users.isLoading ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : users.data && users.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>邮箱</TableHead>
                <TableHead>姓名</TableHead>
                <TableHead>角色</TableHead>
                <TableHead className="text-right">注册时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.data.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-mono text-sm">{u.email}</TableCell>
                  <TableCell className="font-medium">
                    {u.name}
                    {String(u.id) === me.user_id && (
                      <Badge variant="secondary" className="ml-2 text-[10px]">
                        你
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <Select
                      value={u.role}
                      disabled={setRole.isPending}
                      onValueChange={(v) => void changeRole(u, v as Role)}
                    >
                      <SelectTrigger size="sm" className="w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ROLE_DESIGNER}>{roleLabel(ROLE_DESIGNER)}</SelectItem>
                        <SelectItem value={ROLE_MANAGER}>{roleLabel(ROLE_MANAGER)}</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right font-mono text-xs">
                    {u.created_at.slice(0, 10)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="py-16 text-center text-sm text-muted-foreground">暂无用户。</div>
        )}
      </Card>
    </div>
  )
}
