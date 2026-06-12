import { Link } from 'react-router-dom'

const STYLES = [
  { id: 'linear', name: '1 · Linear 系', desc: '精致暗色 + 微妙辉光 + 锐利栅格 + 蓝紫 accent，键盘优先的冷静工具感' },
  { id: 'geist', name: '2 · Vercel / Geist 系', desc: '极致黑白 + 几何 + 高对比 + 等宽细节，极简硬朗' },
  { id: 'claude', name: '3 · Anthropic / Claude 系', desc: '暖米底 + 陶土 accent + 衬线标题 + 大留白，平静亲和有温度' },
  { id: 'glass', name: '4 · 光洁浅色 SaaS 系', desc: '浅灰底 + 玻璃微质感 + 单一蓝紫 accent + 圆润克制（Raycast-light）' },
]

/** UI 风格预览索引（DEV only，throwaway）：Western AI-product 4 方向，同画布（出图工作台满态）。 */
export function StylePreviewIndex() {
  return (
    <div className="mx-auto max-w-xl p-10">
      <h1 className="text-xl font-bold">UI 风格预览 · 第二轮（Western AI-product）</h1>
      <p className="mt-1 text-sm text-muted-foreground">同一张出图工作台满态画布 × 4 个参照锚（DEV only）</p>
      <div className="mt-6 space-y-3">
        {STYLES.map((s) => (
          <Link
            key={s.id}
            to={`/style-preview/${s.id}`}
            className="block rounded-xl border p-4 transition-colors hover:border-primary"
          >
            <div className="font-semibold">{s.name}</div>
            <div className="mt-0.5 text-[13px] text-muted-foreground">{s.desc}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}
