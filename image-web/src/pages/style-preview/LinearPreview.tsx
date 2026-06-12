import {
  PREVIEW_GROUPS, PREVIEW_MODIFIERS, PREVIEW_OVERLAYS, PREVIEW_PLAN, PREVIEW_PROMPT,
  PREVIEW_RESULTS, PREVIEW_UPLOAD,
} from './preview-data'

const ACCENT = '#5e6ad2'
const PANEL = 'border border-[#26282e] bg-[#141519]'
const MUTED = 'text-[#8a8f98]'
const LABEL = 'text-[11px] font-medium uppercase tracking-[0.08em] text-[#62666e]'

/** 风格 1「Linear 系」：精致暗色 + 微妙辉光 + 锐利栅格 + 克制灰阶 + 蓝紫 accent，
 *  键盘优先的冷静工具感。 */
export function LinearPreview() {
  return (
    <div className="relative min-h-screen bg-[#0b0c0f] text-[#e6e7ea] antialiased">
      {/* 微妙辉光：右上蓝紫 radial，近乎不可见 */}
      <div
        className="pointer-events-none absolute right-0 top-0 h-[420px] w-[640px]"
        style={{ background: `radial-gradient(ellipse at 80% 0%, ${ACCENT}1f, transparent 65%)` }}
      />

      <header className="relative flex items-center justify-between border-b border-[#1f2126] px-6 py-3">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2.5">
            <span
              className="grid size-6 place-items-center rounded-[6px] text-[11px] font-semibold text-white"
              style={{ background: `linear-gradient(135deg, ${ACCENT}, #8b7cf0)` }}
            >
              朴
            </span>
            <span className="text-[14px] font-semibold tracking-[-0.01em]">实朴</span>
            <span className={`${MUTED} text-[13px]`}>/ 商品套图</span>
          </div>
          <nav className="flex items-center gap-1 text-[13px]">
            {['工作台', '历史', '客户'].map((n, i) => (
              <span
                key={n}
                className={`rounded-[6px] px-2.5 py-1 ${i === 0 ? 'bg-[#1b1d22] text-[#e6e7ea]' : MUTED}`}
              >
                {n}
              </span>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <span className={`flex items-center gap-1.5 rounded-[6px] border border-[#26282e] px-2 py-1 text-[12px] ${MUTED}`}>
            搜索 <kbd className="rounded-[4px] border border-[#2e3138] bg-[#1b1d22] px-1 font-sans text-[10.5px]">⌘K</kbd>
          </span>
          <span className="rounded-[6px] border border-[#26282e] px-2 py-1 text-[12px]">
            <span className={MUTED}>免费额度</span> <span className="font-medium text-[#9da2ff]">5 张</span>
          </span>
          <span className="grid size-7 place-items-center rounded-full border border-[#2e3138] bg-[#1b1d22] text-[11.5px]">
            朴
          </span>
        </div>
      </header>

      <div className="relative flex">
        {/* 侧栏 */}
        <aside className="w-[200px] shrink-0 border-r border-[#1f2126] px-3 py-4">
          <div className={`${LABEL} px-2 pb-2`}>出图模块</div>
          {[
            { label: '商品套图', on: true },
            { label: '爆款图复刻', on: false },
            { label: '二次编辑', on: false },
          ].map((m) => (
            <div
              key={m.label}
              className={`mb-0.5 flex items-center gap-2 rounded-[6px] px-2 py-1.5 text-[13px] ${
                m.on ? 'bg-[#1b1d22] font-medium' : MUTED
              }`}
            >
              <span
                className="size-1.5 rounded-full"
                style={{ background: m.on ? ACCENT : '#33363d' }}
              />
              {m.label}
            </div>
          ))}
          <div className={`${LABEL} mt-6 px-2 pb-2`}>最近任务</div>
          {['花生礼盒 · 5 张', '润喉糖 · 3 张'].map((t) => (
            <div key={t} className={`px-2 py-1 text-[12.5px] ${MUTED}`}>{t}</div>
          ))}
        </aside>

        {/* 配置面板 */}
        <aside className="w-[340px] shrink-0 border-r border-[#1f2126] p-5">
          <div className={LABEL}>产品原图</div>
          <div className="mt-2 flex gap-2">
            <img src={PREVIEW_UPLOAD} alt="" className="size-14 rounded-[8px] border border-[#26282e] object-cover" />
            <button className={`grid size-14 place-items-center rounded-[8px] border border-dashed border-[#2e3138] text-[16px] ${MUTED}`}>
              +
            </button>
          </div>

          <div className={`${LABEL} mt-5`}>生成设置</div>
          <div className="mt-2 space-y-1.5">
            {PREVIEW_MODIFIERS.map((m) => (
              <div
                key={m.label}
                className="flex items-center justify-between rounded-[8px] border border-[#26282e] bg-[#101114] px-3 py-2 text-[13px]"
              >
                <span className={MUTED}>{m.label}</span>
                <span className="font-medium">{m.value} ⌄</span>
              </div>
            ))}
          </div>

          <div className="mt-5 flex items-baseline justify-between">
            <span className={LABEL}>套图结构</span>
            <span className={`text-[12px] ${MUTED}`}>共 5 张 · 约 ¥2.00</span>
          </div>
          <div className="mt-2 space-y-1.5">
            {PREVIEW_PLAN.map((p) => (
              <div
                key={p.label}
                className="flex items-center justify-between rounded-[8px] border border-[#26282e] bg-[#101114] px-3 py-2"
              >
                <div className="text-[13px]">
                  {p.label}
                  <span className={`ml-2 text-[11.5px] ${MUTED}`}>{p.desc}</span>
                </div>
                <div className="flex items-center overflow-hidden rounded-[6px] border border-[#2e3138]">
                  <button className={`px-1.5 py-0.5 text-[12px] ${MUTED}`}>−</button>
                  <span className="border-x border-[#2e3138] px-2 py-0.5 text-[12.5px] font-medium" style={{ color: '#9da2ff' }}>
                    {p.n}
                  </span>
                  <button className={`px-1.5 py-0.5 text-[12px] ${MUTED}`}>+</button>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {PREVIEW_OVERLAYS.map((t) => (
              <span key={t} className="rounded-[6px] border border-[#2e3138] bg-[#16181d] px-2 py-0.5 text-[11.5px] text-[#b9bdc6]">
                {t} <span className={MUTED}>×</span>
              </span>
            ))}
          </div>

          <div className={`${LABEL} mt-5`}>商品卖点 & 要求</div>
          <p className="mt-2 rounded-[8px] border border-[#26282e] bg-[#101114] p-3 text-[13px] leading-relaxed text-[#b9bdc6]">
            {PREVIEW_PROMPT}
          </p>

          <button
            className="mt-5 flex w-full items-center justify-between rounded-[8px] px-3.5 py-2.5 text-[13.5px] font-medium text-white"
            style={{ background: ACCENT, boxShadow: `0 0 0 1px ${ACCENT}, 0 8px 24px -10px ${ACCENT}cc, inset 0 1px 0 #ffffff2e` }}
          >
            <span>一键生成套图</span>
            <span className="flex items-center gap-2 text-[12px] text-white/75">
              约 ¥2.00 · 5 张
              <kbd className="rounded-[4px] bg-white/15 px-1.5 font-sans text-[10.5px]">⏎</kbd>
            </span>
          </button>
        </aside>

        {/* 结果区 */}
        <main className="flex-1 p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h1 className="text-[17px] font-semibold tracking-[-0.01em]">商品套图</h1>
              <span className="flex items-center gap-1.5 rounded-[6px] border border-[#26282e] px-2 py-0.5 text-[12px]">
                <span className="size-1.5 rounded-full bg-[#4cc38a]" />
                已完成 5/5
              </span>
              <span className={`text-[12.5px] ${MUTED}`}>实付 ¥2.00</span>
            </div>
            <button className="rounded-[6px] border border-[#26282e] px-3 py-1.5 text-[12.5px] text-[#b9bdc6]">
              下载全部
            </button>
          </div>

          {PREVIEW_GROUPS.map((g) => (
            <section key={g.key} className="mt-6">
              <div className="mb-2.5 flex items-baseline gap-2">
                <span className="text-[13px] font-medium">{g.label}</span>
                <span className={`text-[11.5px] ${MUTED}`}>{g.count}</span>
              </div>
              <div className="flex gap-3.5">
                {PREVIEW_RESULTS.filter((r) => r.type === g.key).map((r) => (
                  <div
                    key={r.no}
                    className={`${PANEL} group w-[196px] overflow-hidden rounded-[10px] transition-shadow hover:shadow-[0_0_0_1px_#5e6ad2]`}
                  >
                    <img src={r.src} alt="" className="aspect-square w-full object-cover" />
                    <div className="flex items-center justify-between px-2.5 py-1.5 text-[11.5px]">
                      <span className={MUTED}>{r.cost}</span>
                      <span className="flex gap-2.5">
                        <span className={`cursor-pointer ${MUTED}`}>下载</span>
                        <span className="cursor-pointer" style={{ color: '#9da2ff' }}>再编辑</span>
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
