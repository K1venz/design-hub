import {
  PREVIEW_GROUPS, PREVIEW_MODIFIERS, PREVIEW_OVERLAYS, PREVIEW_PLAN, PREVIEW_PROMPT,
  PREVIEW_RESULTS, PREVIEW_UPLOAD,
} from './preview-data'

const ACCENT = '#5b5bd6'
const GLASS = 'rounded-[16px] border border-white/70 bg-white/75 shadow-[0_8px_32px_-12px_rgba(40,40,90,.12)] backdrop-blur-xl'
const MUTED = 'text-[#6b7080]'
const FAINT = 'text-[#9aa0ad]'

/** 风格 4「光洁浅色 SaaS 系」（Raycast-light）：浅灰底 + 玻璃微质感卡片 +
 *  单一蓝紫 accent + 圆润克制，现代 SaaS 的干净有钱感。 */
export function GlassPreview() {
  return (
    <div className="relative min-h-screen bg-[#f3f4f8] text-[#23262f] antialiased">
      {/* 极淡色斑底 */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(560px 320px at 12% -4%, #5b5bd614, transparent 70%), radial-gradient(620px 360px at 96% 8%, #d65bb010, transparent 70%)',
        }}
      />

      <header className="relative z-10 mx-auto flex max-w-[1380px] items-center justify-between px-7 pt-5">
        <div className={`${GLASS} flex w-full items-center justify-between rounded-full px-4 py-2`}>
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-2">
              <span
                className="grid size-7 place-items-center rounded-[9px] text-[12px] font-bold text-white"
                style={{ background: `linear-gradient(135deg, ${ACCENT}, #8a7bf0)` }}
              >
                朴
              </span>
              <span className="text-[14.5px] font-semibold tracking-[-0.01em]">实朴</span>
            </div>
            <nav className="flex items-center gap-1 text-[13px]">
              {['工作台', '历史', '客户'].map((n, i) => (
                <span
                  key={n}
                  className={`rounded-full px-3 py-1 ${i === 0 ? 'bg-[#23262f] font-medium text-white' : MUTED}`}
                >
                  {n}
                </span>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-[#eef0fb] px-3 py-1 text-[12px] font-medium" style={{ color: ACCENT }}>
              ✦ 免费额度 5 张
            </span>
            <span
              className="grid size-7 place-items-center rounded-full text-[11.5px] font-semibold text-white"
              style={{ background: 'linear-gradient(135deg, #f0a35e, #e0689a)' }}
            >
              朴
            </span>
          </div>
        </div>
      </header>

      <div className="relative z-10 mx-auto flex max-w-[1380px] gap-5 px-7 py-5">
        {/* 模块切换 */}
        <aside className={`${GLASS} h-fit w-[176px] shrink-0 p-2.5`}>
          {[
            { label: '商品套图', icon: '▦', on: true },
            { label: '爆款图复刻', icon: '◈', on: false },
            { label: '二次编辑', icon: '✎', on: false },
          ].map((m) => (
            <div
              key={m.label}
              className={`mb-1 flex items-center gap-2.5 rounded-[11px] px-3 py-2 text-[13px] ${
                m.on ? 'font-semibold text-white' : MUTED
              }`}
              style={m.on ? { background: ACCENT, boxShadow: `0 6px 16px -6px ${ACCENT}99` } : undefined}
            >
              <span className="text-[13px]">{m.icon}</span>
              {m.label}
            </div>
          ))}
          <div className={`mt-3 border-t border-[#e7e9f0] px-3 pb-1 pt-3 text-[11px] ${FAINT}`}>
            最近：花生礼盒 5 张
          </div>
        </aside>

        {/* 配置面板 */}
        <aside className={`${GLASS} w-[352px] shrink-0 p-5`}>
          <FSection title="产品原图" first>
            <div className="flex gap-2">
              <img src={PREVIEW_UPLOAD} alt="" className="size-[60px] rounded-[12px] border border-white object-cover shadow-sm" />
              <button className={`grid size-[60px] place-items-center rounded-[12px] border border-dashed border-[#cfd3e0] bg-white/50 text-[17px] ${FAINT}`}>
                +
              </button>
            </div>
          </FSection>

          <FSection title="生成设置">
            <div className="grid grid-cols-3 gap-2">
              {PREVIEW_MODIFIERS.map((m) => (
                <div key={m.label} className="rounded-[11px] bg-white px-2.5 py-2 shadow-[0_1px_3px_rgba(40,40,90,.06)]">
                  <div className={`text-[10px] ${FAINT}`}>{m.label}</div>
                  <div className="mt-0.5 truncate text-[12px] font-semibold">{m.value}</div>
                </div>
              ))}
            </div>
          </FSection>

          <FSection title="套图结构" right="5 张 · 约 ¥2.00">
            <div className="space-y-1.5">
              {PREVIEW_PLAN.map((p) => (
                <div key={p.label} className="flex items-center justify-between rounded-[12px] bg-white px-3 py-2 shadow-[0_1px_3px_rgba(40,40,90,.06)]">
                  <div className="text-[12.5px] font-medium">
                    {p.label}
                    <span className={`ml-1.5 text-[11px] font-normal ${FAINT}`}>{p.desc}</span>
                  </div>
                  <div className="flex items-center gap-1 rounded-full bg-[#f0f1f7] p-0.5">
                    <button className={`grid size-5 place-items-center rounded-full bg-white text-[11px] shadow-sm ${MUTED}`}>−</button>
                    <span className="w-4 text-center text-[12.5px] font-bold" style={{ color: ACCENT }}>{p.n}</span>
                    <button className={`grid size-5 place-items-center rounded-full bg-white text-[11px] shadow-sm ${MUTED}`}>+</button>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {PREVIEW_OVERLAYS.map((t) => (
                <span key={t} className="rounded-full bg-[#eef0fb] px-2.5 py-1 text-[11.5px] font-medium" style={{ color: ACCENT }}>
                  {t} ×
                </span>
              ))}
            </div>
          </FSection>

          <FSection title="商品卖点 & 要求">
            <p className="rounded-[12px] bg-white p-3 text-[12.5px] leading-relaxed text-[#4a4e5a] shadow-[0_1px_3px_rgba(40,40,90,.06)]">
              {PREVIEW_PROMPT}
            </p>
          </FSection>

          <button
            className="mt-5 w-full rounded-[13px] py-3 text-[13.5px] font-semibold text-white"
            style={{
              background: `linear-gradient(135deg, ${ACCENT}, #7b6cf0)`,
              boxShadow: `0 10px 26px -10px ${ACCENT}b3, inset 0 1px 0 #ffffff40`,
            }}
          >
            一键生成套图 <span className="ml-1 text-[12px] font-medium text-white/80">约 ¥2.00 · 5 张</span>
          </button>
          <p className={`mt-2 text-center text-[11px] ${FAINT}`}>按成功张数计费 · 失败不计</p>
        </aside>

        {/* 结果区 */}
        <main className="flex-1">
          <div className={`${GLASS} flex items-center justify-between px-5 py-3`}>
            <div className="flex items-center gap-3">
              <h1 className="text-[17px] font-semibold tracking-[-0.01em]">商品套图</h1>
              <span className="flex items-center gap-1.5 rounded-full bg-[#e9f9ef] px-2.5 py-0.5 text-[11.5px] font-semibold text-[#1da55b]">
                ● 已完成 5/5
              </span>
              <span className={`text-[12px] ${MUTED}`}>实付 ¥2.00</span>
            </div>
            <button
              className="rounded-full px-3.5 py-1.5 text-[12px] font-semibold text-white"
              style={{ background: '#23262f' }}
            >
              下载全部
            </button>
          </div>

          {PREVIEW_GROUPS.map((g) => (
            <section key={g.key} className="mt-5">
              <div className="mb-2.5 flex items-baseline gap-2 px-1">
                <span className="text-[13.5px] font-semibold">{g.label}</span>
                <span className={`text-[11.5px] ${FAINT}`}>{g.count} 张</span>
              </div>
              <div className="flex gap-4">
                {PREVIEW_RESULTS.filter((r) => r.type === g.key).map((r) => (
                  <div
                    key={r.no}
                    className="group w-[200px] overflow-hidden rounded-[16px] border border-white/70 bg-white shadow-[0_6px_24px_-10px_rgba(40,40,90,.14)] transition-transform hover:-translate-y-0.5"
                  >
                    <img src={r.src} alt="" className="aspect-square w-full object-cover" />
                    <div className="flex items-center justify-between px-3 py-2 text-[11.5px]">
                      <span className={FAINT}>{r.cost}</span>
                      <span className="flex gap-1.5">
                        <button className={`rounded-full bg-[#f0f1f7] px-2.5 py-0.5 font-medium ${MUTED}`}>下载</button>
                        <button className="rounded-full px-2.5 py-0.5 font-semibold text-white" style={{ background: ACCENT }}>
                          再编辑
                        </button>
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </main>
      </div>
    </div>
  )
}

function FSection({
  title, right, first, children,
}: { title: string; right?: string; first?: boolean; children: React.ReactNode }) {
  return (
    <section className={first ? '' : 'mt-4'}>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-[12.5px] font-semibold">{title}</span>
        {right && <span className="text-[11px] text-[#9aa0ad]">{right}</span>}
      </div>
      {children}
    </section>
  )
}
