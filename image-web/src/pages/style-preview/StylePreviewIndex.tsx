import { Link } from 'react-router-dom'

const STYLES = [
  { id: 'editorial', name: 'A · 胶版工作室', desc: '暖纸底 + 衬线大标题 + 细线网格 + 编号工序，杂志制版间的匠气' },
  { id: 'console', name: 'B · 霓虹操控台', desc: '墨黑玻璃面板 + 霓青高光 + 等宽数字，渲染引擎的力量感' },
  { id: 'pop', name: 'C · 果冻商城', desc: '高饱和渐变 + 大圆角贴纸徽标 + 醒目价签，电商能量拉满' },
  { id: 'ink', name: 'D · 青墨宣纸', desc: '宣纸纹 + 青墨 + 印章红点睛，与「实朴」同气质的东方现代' },
]

/** UI 风格预览索引（DEV only，throwaway）：4 个方向同画布（出图工作台满态）。 */
export function StylePreviewIndex() {
  return (
    <div className="mx-auto max-w-xl p-10">
      <h1 className="text-xl font-bold">UI 风格预览（throwaway · DEV only）</h1>
      <p className="mt-1 text-sm text-muted-foreground">同一张出图工作台满态画布 × 4 个设计语言</p>
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
