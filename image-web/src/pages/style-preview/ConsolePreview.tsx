import {
  PREVIEW_GROUPS, PREVIEW_MODIFIERS, PREVIEW_OVERLAYS, PREVIEW_PLAN, PREVIEW_PROMPT,
  PREVIEW_RESULTS, PREVIEW_UPLOAD,
} from './preview-data'

const CYAN = '#2ce0c8'
const PANEL = 'border border-[#1d2935] bg-[#0f151c]/90'
const LABEL = 'text-[10px] uppercase tracking-[0.22em] text-[#52677a]'

/** 风格 B「霓虹操控台」：墨黑玻璃面板 + 霓青高光 + 等宽数字，渲染引擎控制台的力量感。 */
export function ConsolePreview() {
  return (
    <div
      className="min-h-screen bg-[#0a0e13] text-[#d8e3ec] antialiased"
      style={{
        backgroundImage: 'radial-gradient(circle, #16202b 1px, transparent 1px)',
        backgroundSize: '26px 26px',
      }}
    >
      {/* 顶栏 */}
      <header className="flex items-center justify-between border-b border-[#1d2935] bg-[#0a0e13]/80 px-7 py-3.5 backdrop-blur">
        <div className="flex items-center gap-3.5">
          <span
            className="grid size-8 place-items-center rounded-[6px] text-[14px] font-bold text-[#06231e]"
            style={{ background: CYAN, boxShadow: `0 0 18px ${CYAN}55` }}
          >
            朴
          </span>
          <div>
            <div className="text-[15px] font-semibold tracking-[0.12em]">实朴 SHIPU</div>
            <div className="text-[9px] uppercase tracking-[0.3em] text-[#52677a]">E-commerce Image Engine</div>
          </div>
          <span className="ml-4 flex items-center gap-1.5 rounded-[4px] border border-[#1d2935] px-2 py-1 font-mono text-[10.5px] text-[#7e93a6]">
            <span className="size-1.5 rounded-full" style={{ background: CYAN, boxShadow: `0 0 8px ${CYAN}` }} />
            ENGINE · gpt-image-2 READY
          </span>
        </div>
        <nav className="flex items-center gap-6 text-[13px]">
          <span className="font-medium" style={{ color: CYAN }}>工作台</span>
          <span className="text-[#7e93a6]">历史</span>
          <span className="text-[#7e93a6]">客户</span>
          <span className="rounded-[4px] border border-[#1d2935] px-2.5 py-1 font-mono text-[11.5px] text-[#b7f24a]">
            CREDIT 5<span className="ml-1 text-[#52677a]">FREE</span>
          </span>
          <span className="grid size-8 place-items-center rounded-[6px] border border-[#1d2935] bg-[#0f151c] text-[12px]">
            朴
          </span>
        </nav>
      </header>

      <div className="flex gap-5 p-5">
        {/* 模块列（rail） */}
        <aside className={`${PANEL} flex w-[88px] shrink-0 flex-col items-center gap-2 rounded-[10px] py-4`}>
          {[
            { code: 'SET', label: '商品套图', on: true },
            { code: 'CLN', label: '爆款复刻', on: false },
            { code: 'EDT', label: '二次编辑', on: false },
          ].map((m) => (
            <div
              key={m.code}
              className={`relative flex w-[68px] flex-col items-center gap-1 rounded-[8px] py-2.5 ${m.on ? 'bg-[#13202a]' : ''}`}
            >
              {m.on && (
                <span
                  className="absolute left-0 top-2 h-[calc(100%-16px)] w-[2px] rounded-full"
                  style={{ background: CYAN, boxShadow: `0 0 10px ${CYAN}` }}
                />
              )}
              <span className={`font-mono text-[11px] ${m.on ? '' : 'text-[#52677a]'}`} style={m.on ? { color: CYAN } : undefined}>
                {m.code}
              </span>
              <span className={`text-[10.5px] ${m.on ? 'text-[#d8e3ec]' : 'text-[#52677a]'}`}>{m.label}</span>
            </div>
          ))}
        </aside>

        {/* 参数面板 */}
        <aside className={`${PANEL} w-[348px] shrink-0 rounded-[10px] p-5`}>
          <div className={LABEL}>// INPUT</div>
          <div className="mt-2 flex gap-2">
            <img src={PREVIEW_UPLOAD} alt="" className="size-16 rounded-[6px] border border-[#1d2935] object-cover" />
            <div className="grid size-16 place-items-center rounded-[6px] border border-dashed border-[#27384a] text-[18px] text-[#52677a]">
              +
            </div>
          </div>

          <div className={`mt-5 ${LABEL}`}>// PARAMS</div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {PREVIEW_MODIFIERS.map((m) => (
              <div key={m.label} className="rounded-[6px] border border-[#1d2935] bg-[#0c1117] px-2.5 py-2">
                <div className="text-[9.5px] tracking-[0.14em] text-[#52677a]">{m.label}</div>
                <div className="mt-0.5 truncate text-[12px] font-medium">{m.value}</div>
              </div>
            ))}
          </div>

          <div className={`mt-5 ${LABEL}`}>// PLATE PLAN</div>
          <div className="mt-2 space-y-1.5">
            {PREVIEW_PLAN.map((p) => (
              <div key={p.label} className="flex items-center justify-between rounded-[6px] border border-[#1d2935] bg-[#0c1117] px-3 py-2">
                <div className="text-[12.5px]">
                  {p.label}
                  <span className="ml-2 text-[10.5px] text-[#52677a]">{p.desc}</span>
                </div>
                <div className="flex items-center gap-2">
                  <button className="grid size-5 place-items-center rounded-[4px] border border-[#27384a] text-[11px] text-[#7e93a6]">−</button>
                  <span className="w-4 text-center font-mono text-[14px]" style={{ color: CYAN }}>{p.n}</span>
                  <button className="grid size-5 place-items-center rounded-[4px] border border-[#27384a] text-[11px] text-[#7e93a6]">＋</button>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {PREVIEW_OVERLAYS.map((t) => (
              <span key={t} className="rounded-[4px] border border-[#1d2935] px-2 py-0.5 font-mono text-[10.5px] text-[#b7f24a]">
                "{t}"
              </span>
            ))}
          </div>

          <div className={`mt-5 ${LABEL}`}>// BRIEF</div>
          <p className="mt-2 rounded-[6px] border border-[#1d2935] bg-[#0c1117] p-3 text-[12.5px] leading-relaxed text-[#aebccb]">
            {PREVIEW_PROMPT}
          </p>

          <button
            className="mt-5 flex w-full items-center justify-between rounded-[8px] px-4 py-3 text-[#06231e]"
            style={{
              background: `linear-gradient(90deg, ${CYAN}, #19b9a6)`,
              boxShadow: `0 0 28px ${CYAN}40, inset 0 1px 0 #ffffff50`,
            }}
          >
            <span className="text-[14px] font-bold tracking-[0.08em]">RENDER · 一键生成套图</span>
            <span className="font-mono text-[12.5px] font-semibold">¥2.00 / 5 IMG</span>
          </button>
        </aside>

        {/* 输出区 */}
        <main className="relative flex-1">
          {/* 角标括号装饰 */}
          <span className="pointer-events-none absolute -left-1 -top-1 size-5 border-l-2 border-t-2 border-[#27384a]" />
          <span className="pointer-events-none absolute -right-1 -top-1 size-5 border-r-2 border-t-2 border-[#27384a]" />

          <div className="flex items-end justify-between px-1">
            <div>
              <h1 className="text-[24px] font-semibold tracking-[0.04em]">商品套图</h1>
              <div className="mt-1 flex items-center gap-3 font-mono text-[11px] text-[#52677a]">
                <span style={{ color: CYAN }}>JOB #62FCC2C7</span>
                <span>STATUS: COMPLETED 5/5</span>
                <span className="text-[#b7f24a]">COST ¥2.00</span>
              </div>
            </div>
            <button className="rounded-[6px] border border-[#27384a] px-3.5 py-2 text-[12.5px] text-[#aebccb]">
              ↓ 下载全部
            </button>
          </div>
          <div className="mt-3 h-[2px] overflow-hidden rounded-full bg-[#13202a]">
            <div className="h-full w-full" style={{ background: `linear-gradient(90deg, ${CYAN}, #b7f24a)` }} />
          </div>

          {PREVIEW_GROUPS.map((g, gi) => (
            <section key={g.key} className="mt-5 px-1">
              <div className="mb-2.5 flex items-baseline gap-2.5">
                <span className="font-mono text-[11px]" style={{ color: CYAN }}>
                  [{String(gi + 1).padStart(2, '0')}]
                </span>
                <span className="text-[14px] font-semibold">{g.label}</span>
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#52677a]">
                  {g.latin} ×{g.count}
                </span>
              </div>
              <div className="flex gap-4">
                {PREVIEW_RESULTS.filter((r) => r.type === g.key).map((r) => (
                  <div
                    key={r.no}
                    className="group w-[206px] overflow-hidden rounded-[10px] border border-[#1d2935] bg-[#0f151c]"
                  >
                    <img src={r.src} alt="" className="aspect-square w-full object-cover" />
                    <div className="flex items-center justify-between px-2.5 py-2 font-mono text-[10.5px] text-[#7e93a6]">
                      <span>IMG_{r.no}</span>
                      <span>
                        <span className="cursor-pointer" style={{ color: CYAN }}>下载</span>
                        <span className="mx-1.5 text-[#27384a]">|</span>
                        <span className="cursor-pointer text-[#b7f24a]">再编辑</span>
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
