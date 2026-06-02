import { PlusIcon, UsersIcon } from 'lucide-react'

import { useCustomers } from '@/api/customers'
import { CreateCustomerDialog } from '@/components/project/CreateCustomerDialog'
import { CreateProjectDialog } from '@/components/project/CreateProjectDialog'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export function CustomersPage() {
  const customers = useCustomers()

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-xl font-semibold tracking-tight text-foreground">客户</h2>
          <p className="text-sm text-muted-foreground">客户档案跨项目复用，记录品牌色、常用风格与禁忌。</p>
        </div>
        <CreateCustomerDialog
          trigger={
            <Button>
              <PlusIcon className="size-4" />
              新建客户
            </Button>
          }
        />
      </div>

      <Card className="overflow-hidden p-0">
        {customers.isLoading ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : customers.data && customers.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>客户名称</TableHead>
                <TableHead>联系人</TableHead>
                <TableHead>行业</TableHead>
                <TableHead>品牌色</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {customers.data.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-medium">{c.name}</TableCell>
                  <TableCell className="text-muted-foreground">{c.contact || '—'}</TableCell>
                  <TableCell className="text-muted-foreground">{c.industry || '—'}</TableCell>
                  <TableCell>
                    {c.brand_color ? (
                      <span className="flex items-center gap-2">
                        <span
                          className="size-4 rounded-full border"
                          style={{ background: c.brand_color }}
                        />
                        <span className="font-mono text-xs text-muted-foreground">
                          {c.brand_color}
                        </span>
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <CreateProjectDialog
                      defaultCustomerId={c.id}
                      trigger={
                        <Button variant="ghost" size="sm">
                          新建项目
                        </Button>
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="bg-muted text-muted-foreground flex size-12 items-center justify-center rounded-xl">
              <UsersIcon className="size-6" strokeWidth={1.6} />
            </div>
            <p className="text-sm text-muted-foreground">还没有客户，先新建一个吧。</p>
            <CreateCustomerDialog
              trigger={
                <Button variant="outline" size="sm">
                  <PlusIcon className="size-4" />
                  新建客户
                </Button>
              }
            />
          </div>
        )}
      </Card>
    </div>
  )
}
