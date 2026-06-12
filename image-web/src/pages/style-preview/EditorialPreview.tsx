import {
  PREVIEW_GROUPS, PREVIEW_MODIFIERS, PREVIEW_OVERLAYS, PREVIEW_PLAN, PREVIEW_PROMPT,
  PREVIEW_RESULTS, PREVIEW_UPLOAD,
} from './preview-data'

const SERIF = "font-['Fraunces','Songti_SC','STSong',Georgia,serif]"
const INK = 'text-[#1b1611]'
const RULE = 'border-[#d9d0bf]'
const RED = '#bf3a21'

/** 风格 A「胶版工作室」：暖纸底 + 衬线大标题 + 细线网格 + 编号工序，杂志制版间的匠气。 */
export function EditorialPreview() {
  return (
    <div className={`min-h-screen bg-[#f7f3ec] ${INK} antialiased`}>
      {/* 报头：双细线 masthead */}
      <header className="px-10 pt-5">
        <div className="flex items-end justify-between pb-3">
          <div className="flex items-baseline gap-4">
            <span className={`${SERIF} text-[28px] font-semibold tracking-[0.08em]`}>实朴</span>
            <span className="text-[11px] uppercase tracking-[0.32em] text-[#8a8070]">
              SHIPU · 电商图片工作站
            </span>
          </div>
          <nav className="flex items-baseline gap-7 text-[13.5px]">
            <span className="border-b-2 pb-0.5 font-medium" style={{ borderColor: RED }}>工作台</span>
            <span className="text-[#6f675a]">历史</span>
            <span className="text-[#6f675a]">客户</span>
            <span className="ml-3 border px-2.5 py-1 text-[12px] tracking-wide text-[#6f675a]">
              免费额度 · 余 5 张
            </span>
            <span className={`${SERIF} grid size-8 place-items-center rounded-full bg-[#1b1611] text-[13px] text-[#f7f3ec]`}>
              朴
            </span>
          </nav>
        </div>
        <div className={`border-t ${RULE}`} />
        <div className={`mt-[3px] border-t-2 border-[#1b1611]`} />
      </header>

      <div className="flex gap-0 px-10">
        {/* 工序目录（rail） */}
        <aside className={`w-[148px] shrink-0 border-r ${RULE} py-8 pr-6`}>
          {[
            { no: 'Ⅰ', label: '商品套图', on: true },
            { no: 'Ⅱ', label: '爆款图复刻', on: false },
            { no: 'Ⅲ', label: '二次编辑', on: false },
          ].map((it) => (
            <div key={it.label} className="mb-6">
              <div className={`${SERIF} text-[15px] ${it.on ? '' : 'text-[#a39a87]'}`}>{it.no}</div>
              <div
                className={`mt-0.5 text-[13.5px] ${it.on ? 'font-semibold' : 'text-[#a39a87]'}`}
                style={it.on ? { color: RED } : undefined}
              >
                {it.label}
              </div>
              {it.on && <div className="mt-1.5 h-px w-7" style={{ background: RED }} />}
            </div>
          ))}
          <p className="mt-16 text-[10.5px] leading-relaxed tracking-[0.18em] text-[#a39a87]">
            制版间
            <br />
            PLATE ROOM
            <br />
            NO.0612
          </p>
        </aside>

        {/* 配置：编号工序单 */}
        <aside className={`w-[360px] shrink-0 border-r ${RULE} py-8 pl-8 pr-9`}>
          <Section no="01" title="产品原图" latin="MATERIAL">
            <div className="flex gap-2.5">
              <img src={PREVIEW_UPLOAD} alt="" className={`size-[72px] border ${RULE} object-cover`} />
              <div className={`grid size-[72px] place-items-center border border-dashed ${RULE} text-[20px] text-[#a39a87]`}>
                +
              </div>
            </div>
          </Section>

          <Section no="02" title="生成设置" latin="SETTINGS">
            <div className="space-y-2">
              {PREVIEW_MODIFIERS.map((m) => (
                <div key={m.label} className={`flex items-baseline justify-between border-b ${RULE} pb-1.5 text-[13.5px]`}>
                  <span className="text-[#6f675a]">{m.label}</span>
                  <span className="font-medium">{m.value} ▾</span>
                </div>
              ))}
            </div>
          </Section>

          <Section no="03" title="套图结构" latin="PLATE PLAN" right="计 5 张">
            <div className="space-y-2.5">
              {PREVIEW_PLAN.map((p) => (
                <div key={p.label} className="flex items-center justify-between text-[13.5px]">
                  <div>
                    <span className="font-medium">{p.label}</span>
                    <span className="ml-2 text-[11.5px] text-[#a39a87]">{p.desc}</span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <button className={`grid size-5 place-items-center border ${RULE} text-[12px]`}>−</button>
                    <span className={`${SERIF} w-3 text-center text-[15px]`}>{p.n}</span>
                    <button className={`grid size-5 place-items-center border ${RULE} text-[12px]`}>＋</button>
                  </div>
                </div>
              ))}
              <div className="flex flex-wrap gap-1.5 pt-1">
                {PREVIEW_OVERLAYS.map((t) => (
                  <span key={t} className={`border ${RULE} bg-white px-2 py-0.5 text-[12px]`}>
                    「{t}」
                  </span>
                ))}
                <span className="px-1 py-0.5 text-[12px] text-[#a39a87]">图上文案 ≤2 条</span>
              </div>
            </div>
          </Section>

          <Section no="04" title="卖点与要求" latin="BRIEF">
            <p className={`border ${RULE} bg-white p-3 text-[13.5px] leading-relaxed`}>{PREVIEW_PROMPT}</p>
          </Section>

          <button
            className="mt-7 flex w-full items-baseline justify-between bg-[#1b1611] px-4 py-3.5 text-[#f7f3ec]"
            style={{ borderRadius: 2 }}
          >
            <span className="text-[14.5px] font-semibold tracking-[0.06em]">一键生成套图</span>
            <span className={`${SERIF} text-[13px]`}>约 ¥2.00 · 5 张</span>
          </button>
          <p className="mt-2 text-center text-[11px] tracking-[0.14em] text-[#a39a87]">
            按实际成功张数计费 · 失败不计
          </p>
        </aside>

        {/* 结果：印样 contact sheet */}
        <main className="flex-1 py-8 pl-9">
          <div className="flex items-end justify-between">
            <div>
              <h1 className={`${SERIF} text-[30px] font-semibold leading-none`}>商品套图</h1>
              <p className="mt-1.5 text-[11px] uppercase tracking-[0.3em] text-[#8a8070]">
                Proof Sheet · 5 of 5 Completed
              </p>
            </div>
            <div className="flex items-baseline gap-5 text-[13px]">
              <span className="text-[#6f675a]">
                实付 <span className={`${SERIF} text-[15px] ${INK}`}>¥2.00</span>
              </span>
              <button className={`border border-[#1b1611] px-3.5 py-1.5 text-[12.5px] font-medium`}>
                下载全部
              </button>
            </div>
          </div>
          <div className={`mt-4 border-t ${RULE}`} />

          {PREVIEW_GROUPS.map((g) => (
            <section key={g.key} className="mt-6">
              <div className="mb-3 flex items-baseline gap-3">
                <span className={`${SERIF} text-[17px] font-semibold`}>{g.label}</span>
                <span className="text-[10.5px] uppercase tracking-[0.26em] text-[#a39a87]">
                  {g.latin} · {g.count}
                </span>
                <span className="h-px flex-1 self-center bg-[#e4dccb]" />
              </div>
              <div className="flex gap-5">
                {PREVIEW_RESULTS.filter((r) => r.type === g.key).map((r) => (
                  <figure key={r.no} className={`w-[210px] border ${RULE} bg-white p-2 pb-1.5`}>
                    <img src={r.src} alt="" className="aspect-square w-full object-cover" />
                    <figcaption className="flex items-baseline justify-between pt-1.5 text-[11px] text-[#6f675a]">
                      <span className={SERIF}>No.{r.no}</span>
                      <span>
                        <span className="cursor-pointer underline decoration-[#d9d0bf] underline-offset-2">下载</span>
                        <span className="mx-1 text-[#d9d0bf]">/</span>
                        <span className="cursor-pointer underline decoration-[#d9d0bf] underline-offset-2" style={{ color: RED }}>
                          再编辑
                        </span>
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

function Section({
  no, title, latin, right, children,
}: { no: string; title: string; latin: string; right?: string; children: React.ReactNode }) {
  return (
    <section className="mb-7">
      <div className="mb-2.5 flex items-baseline gap-2.5">
        <span className={`${SERIF} text-[15px]`} style={{ color: RED }}>{no}</span>
        <span className="text-[14px] font-semibold tracking-[0.04em]">{title}</span>
        <span className="text-[9.5px] uppercase tracking-[0.26em] text-[#a39a87]">{latin}</span>
        {right && <span className="ml-auto text-[12px] text-[#6f675a]">{right}</span>}
      </div>
      {children}
    </section>
  )
}
