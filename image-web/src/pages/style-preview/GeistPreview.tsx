import {
  PREVIEW_GROUPS, PREVIEW_MODIFIERS, PREVIEW_OVERLAYS, PREVIEW_PLAN, PREVIEW_PROMPT,
  PREVIEW_RESULTS, PREVIEW_UPLOAD,
} from './preview-data'

const BORDER = 'border-[#eaeaea]'
const MUTED = 'text-[#666]'
const FAINT = 'text-[#999]'
const BLUE = '#0070f3'
const MONO = 'font-mono tabular'

/** 风格 2「Vercel / Geist 系」：极致黑白 + 几何 + 高对比 + 等宽细节，极简硬朗。 */
export function GeistPreview() {
  return (
    <div className="min-h-screen bg-white text-black antialiased">
      <header className={`flex items-center justify-between border-b ${BORDER} px-6 py-3`}>
        <div className="flex items-center gap-5">
          <div className="flex items-center gap-2.5">
            <span className="size-0 border-x-[9px] border-b-[15px] border-x-transparent border-b-black" />
            <span className="text-[15px] font-semibold tracking-[-0.02em]">实朴</span>
            <span className={`${MONO} text-[10px] uppercase tracking-[0.1em] ${FAINT}`}>shipu.app</span>
          </div>
          <nav className="flex items-center gap-5 text-[13.5px]">
            <span className="relative font-medium">
              工作台
              <span className="absolute -bottom-[15px] left-0 h-[2px] w-full bg-black" />
            </span>
            <span className={MUTED}>历史</span>
            <span className={MUTED}>客户</span>
          </nav>
        </div>
        <div className="flex items-center gap-2.5">
          <span className={`rounded-full border ${BORDER} px-3 py-1 text-[12px] ${MUTED}`}>
            免费额度 <span className={`${MONO} font-medium text-black`}>5</span> 张
          </span>
          <button className="rounded-[6px] bg-black px-3.5 py-1.5 text-[12.5px] font-medium text-white">
            充值
          </button>
          <span className={`grid size-7 place-items-center rounded-full border ${BORDER} text-[11.5px]`}>朴</span>
        </div>
      </header>

      <div className="flex">
        {/* 侧栏 */}
        <aside className={`min-h-[calc(100vh-53px)] w-[190px] shrink-0 border-r ${BORDER} px-4 py-5`}>
          <div className={`pb-2 text-[11px] font-medium uppercase tracking-[0.08em] ${FAINT}`}>Modules</div>
          {[
            { label: '商品套图', on: true },
            { label: '爆款图复刻', on: false },
            { label: '二次编辑', on: false },
          ].map((m) => (
            <div
              key={m.label}
              className={`-mx-2 mb-0.5 rounded-[6px] px-2 py-1.5 text-[13.5px] ${
                m.on ? 'bg-[#fafafa] font-medium' : MUTED
              }`}
            >
              {m.label}
            </div>
          ))}
          <div className={`mt-7 border-t ${BORDER} pt-4 text-[12px] leading-[1.9] ${FAINT}`}>
            <div className={`${MONO} text-[11px]`}>JOB 62FCC2C7</div>
            <div>5 张 · ¥2.00 · 完成</div>
          </div>
        </aside>

        {/* 配置面板 */}
        <aside className={`w-[348px] shrink-0 border-r ${BORDER} p-6`}>
          <GSection title="产品原图" first>
            <div className="flex gap-2">
              <img src={PREVIEW_UPLOAD} alt="" className={`size-14 rounded-[6px] border ${BORDER} object-cover`} />
              <button className={`grid size-14 place-items-center rounded-[6px] border border-dashed ${BORDER} text-[16px] ${FAINT}`}>
                +
              </button>
            </div>
          </GSection>

          <GSection title="生成设置">
            <div className="grid grid-cols-3 gap-2">
              {PREVIEW_MODIFIERS.map((m) => (
                <div key={m.label} className={`rounded-[6px] border ${BORDER} px-2.5 py-2`}>
                  <div className={`text-[10.5px] ${FAINT}`}>{m.label}</div>
                  <div className="mt-0.5 truncate text-[12.5px] font-medium">{m.value}</div>
                </div>
              ))}
            </div>
          </GSection>

          <GSection title="套图结构" right="5 张 · ¥2.00">
            <div className={`divide-y divide-[#eaeaea] rounded-[6px] border ${BORDER}`}>
              {PREVIEW_PLAN.map((p) => (
                <div key={p.label} className="flex items-center justify-between px-3 py-2.5">
                  <div className="text-[13px] font-medium">
                    {p.label}
                    <span className={`ml-2 text-[11.5px] font-normal ${FAINT}`}>{p.desc}</span>
                  </div>
                  <div className={`flex items-center rounded-[6px] border ${BORDER}`}>
                    <button className={`px-2 py-0.5 text-[13px] ${MUTED}`}>−</button>
                    <span className={`${MONO} border-x ${BORDER} px-2.5 py-0.5 text-[13px]`}>{p.n}</span>
                    <button className={`px-2 py-0.5 text-[13px] ${MUTED}`}>+</button>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {PREVIEW_OVERLAYS.map((t) => (
                <span key={t} className={`rounded-full border ${BORDER} bg-[#fafafa] px-2.5 py-0.5 text-[11.5px]`}>
                  {t} <span className={FAINT}>×</span>
                </span>
              ))}
            </div>
          </GSection>

          <GSection title="商品卖点 & 要求">
            <p className={`rounded-[6px] border ${BORDER} bg-[#fafafa] p-3 text-[13px] leading-relaxed text-[#444]`}>
              {PREVIEW_PROMPT}
            </p>
          </GSection>

          <button className="mt-6 flex w-full items-center justify-center gap-3 rounded-[6px] bg-black py-2.5 text-[13.5px] font-medium text-white transition-colors hover:bg-[#333]">
            一键生成套图
            <span className={`${MONO} text-[12px] text-white/60`}>¥2.00 / 5</span>
          </button>
          <p className={`mt-2 text-center text-[11.5px] ${FAINT}`}>按成功张数计费 · 失败不计</p>
        </aside>

        {/* 结果区 */}
        <main className="flex-1 p-7">
          <div className="flex items-end justify-between">
            <div>
              <h1 className="text-[22px] font-semibold tracking-[-0.02em]">商品套图</h1>
              <div className={`mt-1 flex items-center gap-3 text-[12.5px] ${MUTED}`}>
                <span className="flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-[#0cce6b]" />
                  完成 <span className={MONO}>5/5</span>
                </span>
                <span>
                  实付 <span className={`${MONO} text-black`}>¥2.00</span>
                </span>
              </div>
            </div>
            <button className={`rounded-[6px] border ${BORDER} px-3.5 py-1.5 text-[12.5px] font-medium hover:border-black`}>
              下载全部
            </button>
          </div>
          <div className={`mt-4 border-t ${BORDER}`} />

          {PREVIEW_GROUPS.map((g) => (
            <section key={g.key} className="mt-6">
              <div className="mb-2.5 flex items-baseline gap-2.5">
                <span className="text-[13.5px] font-semibold">{g.label}</span>
                <span className={`${MONO} text-[11px] uppercase tracking-[0.08em] ${FAINT}`}>
                  {g.latin} — {g.count}
                </span>
              </div>
              <div className="flex gap-4">
                {PREVIEW_RESULTS.filter((r) => r.type === g.key).map((r) => (
                  <div
                    key={r.no}
                    className={`group w-[198px] overflow-hidden rounded-[8px] border ${BORDER} transition-shadow hover:shadow-[0_4px_16px_rgba(0,0,0,.08)]`}
                  >
                    <img src={r.src} alt="" className="aspect-square w-full object-cover" />
                    <div className={`flex items-center justify-between border-t ${BORDER} px-2.5 py-1.5 text-[11.5px]`}>
                      <span className={`${MONO} ${FAINT}`}>{r.no} · {r.cost}</span>
                      <span className="flex gap-2.5">
                        <span className={`cursor-pointer ${MUTED} hover:text-black`}>下载</span>
                        <span className="cursor-pointer font-medium" style={{ color: BLUE }}>再编辑</span>
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

function GSection({
  title, right, first, children,
}: { title: string; right?: string; first?: boolean; children: React.ReactNode }) {
  return (
    <section className={first ? '' : 'mt-6'}>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-[12px] font-medium uppercase tracking-[0.06em] text-[#666]">{title}</span>
        {right && <span className="font-mono text-[11.5px] text-[#999]">{right}</span>}
      </div>
      {children}
    </section>
  )
}
