import {
  PREVIEW_GROUPS, PREVIEW_MODIFIERS, PREVIEW_OVERLAYS, PREVIEW_PLAN, PREVIEW_PROMPT,
  PREVIEW_RESULTS, PREVIEW_UPLOAD,
} from './preview-data'

const SONG = "font-['Songti_SC','STSong','Noto_Serif_SC',serif]"
const INK = '#21464a'
const INK_DEEP = '#16282b'
const SEAL = '#b3342b'
const LINE = 'border-[#d9d2c0]'
const NUMS = ['壹', '贰', '叁']

/** 风格 D「青墨宣纸」：宣纸纹底 + 青墨 + 印章红点睛，与「实朴」同气质的东方现代。 */
export function InkPreview() {
  return (
    <div className={`paper-grain min-h-screen bg-[#f4efe4] antialiased`} style={{ color: INK_DEEP }}>
      {/* 顶栏：印章 + 字标 */}
      <header className="flex items-end justify-between px-10 pb-4 pt-6">
        <div className="flex items-end gap-3.5">
          <span
            className={`${SONG} grid size-11 place-items-center text-[17px] font-semibold leading-none text-[#f6efe2]`}
            style={{ background: SEAL, borderRadius: 3, boxShadow: 'inset 0 0 6px rgba(0,0,0,.18)' }}
          >
            实朴
          </span>
          <div>
            <div className={`${SONG} text-[24px] font-semibold leading-none tracking-[0.22em]`} style={{ color: INK_DEEP }}>
              实朴工作站
            </div>
            <div className="mt-1.5 text-[10.5px] tracking-[0.4em] text-[#8d927e]">电商图片 · 实在出品</div>
          </div>
        </div>
        <nav className="flex items-baseline gap-2 text-[13.5px]">
          {['工作台', '历史', '客户'].map((n, i) => (
            <span key={n} className="flex items-baseline gap-2">
              {i > 0 && <span className="text-[#c5bda6]">·</span>}
              <span
                className={i === 0 ? `${SONG} font-semibold` : 'text-[#7d8271]'}
                style={i === 0 ? { color: SEAL } : undefined}
              >
                {n}
              </span>
            </span>
          ))}
          <span className={`ml-5 border ${LINE} bg-[#faf6ec] px-2.5 py-1 text-[11.5px] tracking-[0.1em] text-[#7d8271]`} style={{ borderRadius: 3 }}>
            盈余 · 免费五张
          </span>
          <span className={`${SONG} ml-2 grid size-8 place-items-center rounded-full text-[12.5px] text-[#f6efe2]`} style={{ background: INK }}>
            朴
          </span>
        </nav>
      </header>
      <div className={`mx-10 border-t ${LINE}`} />
      <div className="mx-10 mt-[2px] border-t border-[#eee8d8]" />

      <div className="flex gap-8 px-10 py-6">
        {/* 册目（rail） */}
        <aside className="w-[120px] shrink-0 pt-1">
          {[
            { num: '甲', label: '商品套图', on: true },
            { num: '乙', label: '爆款复刻', on: false },
            { num: '丙', label: '二次编辑', on: false },
          ].map((m) => (
            <div key={m.label} className={`mb-5 flex items-center gap-2.5 border-l-2 pl-3 ${m.on ? '' : 'border-transparent'}`} style={m.on ? { borderColor: SEAL } : undefined}>
              <span
                className={`${SONG} grid size-6 place-items-center border text-[11.5px] ${m.on ? 'text-[#f6efe2]' : `${LINE} text-[#a8a48f]`}`}
                style={m.on ? { background: INK, borderColor: INK, borderRadius: 2 } : { borderRadius: 2 }}
              >
                {m.num}
              </span>
              <span className={`text-[13.5px] ${m.on ? `${SONG} font-semibold` : 'text-[#a8a48f]'}`}>{m.label}</span>
            </div>
          ))}
          <p className={`${SONG} mt-14 text-[11px] leading-[1.9] tracking-[0.3em] text-[#b3ae97]`} style={{ writingMode: 'vertical-rl' }}>
            一图一物 · 不事雕琢
          </p>
        </aside>

        {/* 单据（配置面板） */}
        <aside className={`w-[360px] shrink-0 border ${LINE} bg-[#faf6ec] p-6`} style={{ borderRadius: 4, boxShadow: '0 1px 0 #fff inset' }}>
          <InkSection title="产品原图">
            <div className="flex gap-2.5">
              <span className={`border ${LINE} bg-white p-1`} style={{ borderRadius: 3 }}>
                <img src={PREVIEW_UPLOAD} alt="" className="size-16 object-cover" style={{ borderRadius: 2 }} />
              </span>
              <span className={`grid size-[74px] place-items-center border border-dashed ${LINE} text-[18px] text-[#b3ae97]`} style={{ borderRadius: 3 }}>
                ＋
              </span>
            </div>
          </InkSection>

          <InkSection title="生成设置">
            <div className="space-y-2">
              {PREVIEW_MODIFIERS.map((m) => (
                <div key={m.label} className="flex items-baseline justify-between text-[13.5px]">
                  <span className="tracking-[0.2em] text-[#7d8271]">{m.label}</span>
                  <span className={`border-b border-dotted border-[#b3ae97] pb-0.5 font-medium`} style={{ color: INK_DEEP }}>
                    {m.value} ▾
                  </span>
                </div>
              ))}
            </div>
          </InkSection>

          <InkSection title="套图结构" right="共五张">
            <div className="space-y-2.5">
              {PREVIEW_PLAN.map((p) => (
                <div key={p.label} className="flex items-center justify-between text-[13.5px]">
                  <div>
                    <span className="font-medium">{p.label}</span>
                    <span className="ml-2 text-[11px] text-[#a8a48f]">{p.desc}</span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <button className={`grid size-5 place-items-center border ${LINE} bg-white text-[11px] text-[#7d8271]`} style={{ borderRadius: 2 }}>−</button>
                    <span className={`${SONG} w-4 text-center text-[15px]`} style={{ color: SEAL }}>{p.n}</span>
                    <button className={`grid size-5 place-items-center border ${LINE} bg-white text-[11px] text-[#7d8271]`} style={{ borderRadius: 2 }}>＋</button>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {PREVIEW_OVERLAYS.map((t) => (
                <span key={t} className={`${SONG} border ${LINE} bg-white px-2 py-0.5 text-[12px]`} style={{ borderRadius: 2 }}>
                  「{t}」
                </span>
              ))}
            </div>
          </InkSection>

          <InkSection title="卖点要求">
            <p className={`border ${LINE} bg-white p-3 text-[13px] leading-[1.8]`} style={{ borderRadius: 3 }}>
              {PREVIEW_PROMPT}
            </p>
          </InkSection>

          <button
            className={`${SONG} mt-2 flex w-full items-center justify-center gap-3 py-3 text-[15px] font-semibold tracking-[0.3em] text-[#f6efe2]`}
            style={{ background: INK, borderRadius: 3 }}
          >
            一键生成套图
            <span className="size-1.5 rounded-full" style={{ background: SEAL }} />
            <span className="text-[12.5px] tracking-normal opacity-85">约 ¥2.00 · 五张</span>
          </button>
          <p className="mt-2 text-center text-[10.5px] tracking-[0.24em] text-[#a8a48f]">按成计费 · 失败之张分文不取</p>
        </aside>

        {/* 装裱结果区 */}
        <main className="flex-1">
          <div className="flex items-end justify-between">
            <div className="flex items-end gap-4">
              <h1 className={`${SONG} text-[26px] font-semibold leading-none tracking-[0.3em]`}>商品套图</h1>
              <span className="pb-0.5 text-[11.5px] tracking-[0.18em] text-[#7d8271]">五张既成 · 实付 ¥2.00</span>
            </div>
            <button className={`${SONG} border px-4 py-1.5 text-[12.5px] tracking-[0.2em]`} style={{ borderColor: INK, color: INK, borderRadius: 3 }}>
              下载全部
            </button>
          </div>
          <div className={`mt-3.5 border-t ${LINE}`} />

          {PREVIEW_GROUPS.map((g, gi) => (
            <section key={g.key} className="mt-5">
              <div className="mb-3 flex items-center gap-2.5">
                <span className={`${SONG} grid size-5 place-items-center text-[10.5px] text-[#f6efe2]`} style={{ background: INK, borderRadius: 2 }}>
                  {NUMS[gi]}
                </span>
                <span className={`${SONG} text-[16px] font-semibold tracking-[0.14em]`}>{g.label}</span>
                <span className="text-[10.5px] tracking-[0.26em] text-[#a8a48f]">凡 {g.count} 张</span>
              </div>
              <div className="flex gap-5">
                {PREVIEW_RESULTS.filter((r) => r.type === g.key).map((r, i) => (
                  <figure key={r.no} className={`relative border ${LINE} bg-white p-2.5 pb-2`} style={{ borderRadius: 3, boxShadow: '0 1px 2px rgba(33,70,74,.08)' }}>
                    <img src={r.src} alt="" className="aspect-square w-[196px] object-cover" style={{ borderRadius: 2 }} />
                    {gi === 0 && i === 0 && (
                      <span
                        className={`${SONG} absolute -right-2 top-3 px-1 py-1.5 text-[10px] leading-[1.5] text-[#f6efe2]`}
                        style={{ background: SEAL, borderRadius: 2, writingMode: 'vertical-rl' }}
                      >
                        主图之选
                      </span>
                    )}
                    <figcaption className="flex items-baseline justify-between pt-1.5 text-[11px] text-[#7d8271]">
                      <span className={SONG}>其{NUMS[i] ?? i + 1}</span>
                      <span className="flex gap-2">
                        <span className="cursor-pointer border-b border-dotted border-[#b3ae97]">下载</span>
                        <span className="cursor-pointer border-b border-dotted" style={{ color: SEAL, borderColor: SEAL }}>
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

function InkSection({
  title, right, children,
}: { title: string; right?: string; children: React.ReactNode }) {
  return (
    <section className="mb-6">
      <div className="mb-2.5 flex items-baseline">
        <span className={`${SONG} text-[14px] font-semibold tracking-[0.24em]`} style={{ color: INK }}>
          {title}
        </span>
        <span className="ml-3 h-px flex-1 self-center bg-[#e4ddc9]" />
        {right && <span className="ml-3 text-[11px] tracking-[0.2em] text-[#a8a48f]">{right}</span>}
      </div>
      {children}
    </section>
  )
}
