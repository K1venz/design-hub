import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FolderKanbanIcon, PlusIcon } from 'lucide-react'

import { useCustomers } from '@/api/customers'
import { useProjects } from '@/api/projects'
import { CreateCustomerDialog } from '@/components/project/CreateCustomerDialog'
import { CreateProjectDialog } from '@/components/project/CreateProjectDialog'
import { StatusBadge } from '@/components/project/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const ALL = '__all__'

export function WorkbenchPage() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<string>(ALL)
  const customers = useCustomers()
  const projects = useProjects(filter === ALL ? undefined : Number(filter))

  const customerName = useMemo(() => {
    const map = new Map<number, string>()
    for (const c of customers.data ?? []) map.set(c.id, c.name)
    return map
  }, [customers.data])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-xl font-semibold tracking-tight text-foreground">项目工作台</h2>
          <p className="text-sm text-muted-foreground">一单一档：管理客户项目，发起出图、选稿、改稿与交付。</p>
        </div>
        <div className="flex items-center gap-2">
          <CreateCustomerDialog
            trigger={
              <Button variant="outline">
                <PlusIcon className="size-4" />
                新建客户
              </Button>
            }
          />
          <CreateProjectDialog
            trigger={
              <Button>
                <PlusIcon className="size-4" />
                新建项目
              </Button>
            }
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">客户</span>
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-56" size="sm">
            <SelectValue placeholder="全部客户" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>全部客户</SelectItem>
            {(customers.data ?? []).map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card className="overflow-hidden p-0">
        {projects.isLoading ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : projects.data && projects.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>项目</TableHead>
                <TableHead>客户</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">轮次</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {projects.data.map((p) => (
                <TableRow
                  key={p.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/projects/${p.id}`)}
                >
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {customerName.get(p.customer_id) ?? `#${p.customer_id}`}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={p.status} />
                  </TableCell>
                  <TableCell className="text-right tabular font-mono text-sm text-muted-foreground">
                    第 {p.current_round} 轮
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="bg-muted text-muted-foreground flex size-12 items-center justify-center rounded-xl">
              <FolderKanbanIcon className="size-6" strokeWidth={1.6} />
            </div>
            <p className="text-sm text-muted-foreground">
              {filter === ALL ? '还没有项目，新建一个开始吧。' : '该客户暂无项目。'}
            </p>
            <CreateProjectDialog
              defaultCustomerId={filter === ALL ? undefined : Number(filter)}
              trigger={
                <Button variant="outline" size="sm">
                  <PlusIcon className="size-4" />
                  新建项目
                </Button>
              }
            />
          </div>
        )}
      </Card>
    </div>
  )
}
