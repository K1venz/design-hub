import {
  PREVIEW_GROUPS, PREVIEW_MODIFIERS, PREVIEW_OVERLAYS, PREVIEW_PLAN, PREVIEW_PROMPT,
  PREVIEW_RESULTS, PREVIEW_UPLOAD,
} from './preview-data'

const SERIF = "font-['Fraunces',Georgia,'Songti_SC',serif]"
const CLAY = '#c96442'
const INK = 'text-[#26241f]'
const MUTED = 'text-[#73705f]'
const BORDER = 'border-[#e8e2d4]'
const CARD = `rounded-[14px] border ${BORDER} bg-[#fffdf8]`

/** 风格 3「Anthropic / Claude 系」：暖米底 + 陶土 accent + 衬线标题 + 大留白，
 *  平静、亲和、有温度的极简。 */
export function ClaudePreview() {
  return (
    <div className={`min-h-screen bg-[#f5f1e8] ${INK} antialiased`}>
      <header className="mx-auto flex max-w-[1380px] items-center justify-between px-8 pb-2 pt-5">
        <div className="flex items-baseline gap-3">
          <span className={`${SERIF} text-[21px] font-semibold tracking-[-0.01em]`}>实朴</span>
          <span className={`text-[12px] ${MUTED}`}>电商图片工作站</span>
        </div>
        <nav className="flex items-center gap-1.5 text-[13.5px]">
          {['工作台', '历史', '客户'].map((n, i) => (
            <span
              key={n}
              className={`rounded-full px-3.5 py-1.5 ${i === 0 ? 'bg-[#eae3d3] font-medium' : MUTED}`}
            >
              {n}
            </span>
          ))}
          <span className={`ml-3 rounded-full border ${BORDER} bg-[#fffdf8] px-3 py-1.5 text-[12px] ${MUTED}`}>
            免费额度 <span className="font-semibold" style={{ color: CLAY }}>5 张</span>
          </span>
          <span
            className="ml-1.5 grid size-8 place-items-center rounded-full text-[12.5px] font-medium text-white"
            style={{ background: CLAY }}
          >
            朴
          </span>
        </nav>
      </header>

      <div className="mx-auto flex max-w-[1380px] gap-6 px-8 py-5">
        {/* 模块列表 */}
        <aside className="w-[180px] shrink-0 pt-1">
          {[
            { label: '商品套图', desc: '一键整套', on: true },
            { label: '爆款图复刻', desc: '参考重绘', on: false },
            { label: '二次编辑', desc: '基于结果迭代', on: false },
          ].map((m) => (
            <div
              key={m.label}
              className={`mb-2 rounded-[12px] px-3.5 py-2.5 ${m.on ? `border ${BORDER} bg-[#fffdf8] shadow-[0_1px_2px_rgba(60,50,30,.04)]` : ''}`}
            >
              <div className={`text-[13.5px] ${m.on ? 'font-semibold' : MUTED}`}>
                {m.on && <span className="mr-1.5 inline-block size-1.5 rounded-full align-[2px]" style={{ background: CLAY }} />}
                {m.label}
              </div>
              <div className={`mt-0.5 text-[11px] ${m.on ? MUTED : 'text-[#a39f8c]'}`}>{m.desc}</div>
            </div>
          ))}
          <p className={`mt-10 px-1 text-[11.5px] leading-[1.8] ${MUTED}`}>
            上传产品图，
            <br />
            其余交给实朴。
          </p>
        </aside>

        {/* 配置面板 */}
        <aside className={`${CARD} w-[360px] shrink-0 p-6`}>
          <CSection title="产品原图" first>
            <div className="flex gap-2.5">
              <img src={PREVIEW_UPLOAD} alt="" className={`size-16 rounded-[10px] border ${BORDER} object-cover`} />
              <button className={`grid size-16 place-items-center rounded-[10px] border border-dashed border-[#d8d0bc] text-[18px] ${MUTED}`}>
                +
              </button>
            </div>
          </CSection>

          <CSection title="生成设置">
            <div className="space-y-2">
              {PREVIEW_MODIFIERS.map((m) => (
                <div key={m.label} className={`flex items-center justify-between rounded-[10px] bg-[#f5f1e6] px-3.5 py-2.5 text-[13px]`}>
                  <span className={MUTED}>{m.label}</span>
                  <span className="font-medium">{m.value} ⌄</span>
                </div>
              ))}
            </div>
          </CSection>

          <CSection title="套图结构" right="共 5 张">
            <div className="space-y-2">
              {PREVIEW_PLAN.map((p) => (
                <div key={p.label} className="flex items-center justify-between rounded-[10px] bg-[#f5f1e6] px-3.5 py-2.5">
                  <div className="text-[13px] font-medium">
                    {p.label}
                    <span className={`ml-2 text-[11.5px] font-normal ${MUTED}`}>{p.desc}</span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <button className={`grid size-6 place-items-center rounded-full border ${BORDER} bg-[#fffdf8] text-[13px] ${MUTED}`}>−</button>
                    <span className="w-3 text-center text-[14px] font-semibold">{p.n}</span>
                    <button className={`grid size-6 place-items-center rounded-full border ${BORDER} bg-[#fffdf8] text-[13px] ${MUTED}`}>+</button>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {PREVIEW_OVERLAYS.map((t) => (
                <span key={t} className={`rounded-full border ${BORDER} bg-[#fffdf8] px-3 py-1 text-[12px]`}>
                  {t} <span className={MUTED}>×</span>
                </span>
              ))}
            </div>
          </CSection>

          <CSection title="商品卖点与要求">
            <p className="rounded-[10px] bg-[#f5f1e6] p-3.5 text-[13px] leading-[1.7] text-[#4a463a]">
              {PREVIEW_PROMPT}
            </p>
          </CSection>

          <button
            className="mt-6 w-full rounded-[12px] py-3 text-[14px] font-semibold text-white shadow-[0_2px_8px_rgba(201,100,66,.35)]"
            style={{ background: CLAY }}
          >
            一键生成套图 <span className="ml-1.5 text-[12.5px] font-normal text-white/80">5 张</span>
          </button>
          <p className={`mt-2.5 text-center text-[11.5px] ${MUTED}`}>完成后可逐张下载</p>
        </aside>

        {/* 结果区 */}
        <main className="flex-1 pt-1">
          <div className="flex items-end justify-between">
            <div>
              <h1 className={`${SERIF} text-[26px] font-semibold tracking-[-0.01em]`}>商品套图</h1>
              <p className={`mt-1 text-[13px] ${MUTED}`}>5 张全部完成</p>
            </div>
            <button className={`rounded-full border ${BORDER} bg-[#fffdf8] px-4 py-2 text-[12.5px] font-medium`}>
              下载全部
            </button>
          </div>

          {PREVIEW_GROUPS.map((g) => (
            <section key={g.key} className="mt-6">
              <div className="mb-3 flex items-baseline gap-2.5">
                <span className={`${SERIF} text-[16px] font-semibold`}>{g.label}</span>
                <span className={`text-[12px] ${MUTED}`}>{g.count} 张</span>
              </div>
              <div className="flex gap-4">
                {PREVIEW_RESULTS.filter((r) => r.type === g.key).map((r) => (
                  <figure key={r.no} className={`${CARD} w-[204px] overflow-hidden`}>
                    <img src={r.src} alt="" className="aspect-square w-full object-cover" />
                    <figcaption className="flex items-center justify-between px-3 py-2 text-[11.5px]">
                      <span className={MUTED}>#{r.no}</span>
                      <span className="flex gap-2.5">
                        <span className={`cursor-pointer ${MUTED}`}>下载</span>
                        <span className="cursor-pointer font-medium" style={{ color: CLAY }}>再编辑</span>
                      </span>
                    </figcaption>
                  </figure>
                ))}
              </div>
            </section>
          ))}
        </main>
      </div>
    </div>
  )
}

function CSection({
  title, right, first, children,
}: { title: string; right?: string; first?: boolean; children: React.ReactNode }) {
  return (
    <section className={first ? '' : 'mt-5'}>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-[13px] font-semibold">{title}</span>
        {right && <span className="text-[11.5px] text-[#73705f]">{right}</span>}
      </div>
      {children}
    </section>
  )
}
