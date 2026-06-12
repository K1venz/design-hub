import {
  PREVIEW_GROUPS, PREVIEW_MODIFIERS, PREVIEW_OVERLAYS, PREVIEW_PLAN, PREVIEW_PROMPT,
  PREVIEW_RESULTS, PREVIEW_UPLOAD,
} from './preview-data'

const GRAD = 'linear-gradient(95deg, #7c3aed 0%, #ff5d7e 52%, #ffb020 100%)'
const CARD = 'rounded-[22px] border-2 border-[#ffe3d8] bg-white shadow-[0_14px_34px_-18px_rgba(255,93,126,.35)]'

/** 风格 C「果冻商城」：高饱和渐变 + 大圆角贴纸徽标 + 醒目价签，扑面而来的电商能量。 */
export function PopPreview() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-[#fff7f1] via-[#fff1f5] to-[#f6f0ff] text-[#34243e] antialiased">
      {/* 顶栏 */}
      <header className="flex items-center justify-between px-7 py-4">
        <div className="flex items-center gap-3">
          <span
            className="grid size-10 place-items-center rounded-[14px] text-[17px] font-black text-white shadow-[0_8px_20px_-6px_rgba(124,58,237,.5)]"
            style={{ background: GRAD }}
          >
            朴
          </span>
          <div>
            <span className="bg-clip-text text-[19px] font-black text-transparent" style={{ backgroundImage: GRAD }}>
              实朴
            </span>
            <span className="ml-2 text-[12px] font-semibold text-[#9b8aa8]">电商图片工作站</span>
          </div>
          <span className="ml-3 -rotate-2 rounded-[10px] bg-[#ffb020] px-2.5 py-1 text-[11.5px] font-black text-white shadow-[0_6px_14px_-6px_#ffb020]">
            新人免费 5 张 🎁
          </span>
        </div>
        <nav className="flex items-center gap-2.5 text-[13.5px] font-bold">
          <span className="rounded-full px-4 py-1.5 text-white" style={{ background: GRAD }}>工作台</span>
          <span className="rounded-full px-4 py-1.5 text-[#9b8aa8]">历史</span>
          <span className="rounded-full px-4 py-1.5 text-[#9b8aa8]">客户</span>
          <span className="ml-2 grid size-9 place-items-center rounded-full border-2 border-[#ffe3d8] bg-white text-[13px] font-black text-[#7c3aed]">
            朴
          </span>
        </nav>
      </header>

      <div className="flex gap-5 px-7 pb-7">
        {/* 玩法选择（rail） */}
        <aside className="flex w-[104px] shrink-0 flex-col gap-3">
          {[
            { emoji: '🧺', label: '商品套图', on: true },
            { emoji: '🔥', label: '爆款复刻', on: false },
            { emoji: '✏️', label: '二次编辑', on: false },
          ].map((m) => (
            <div
              key={m.label}
              className={`flex flex-col items-center gap-1.5 rounded-[18px] border-2 py-3.5 ${
                m.on
                  ? 'border-transparent text-white shadow-[0_10px_24px_-10px_rgba(124,58,237,.55)]'
                  : 'border-[#ffe3d8] bg-white text-[#9b8aa8]'
              }`}
              style={m.on ? { background: GRAD } : undefined}
            >
              <span className="text-[20px]">{m.emoji}</span>
              <span className="text-[11.5px] font-bold">{m.label}</span>
            </div>
          ))}
        </aside>

        {/* 配置卡 */}
        <aside className={`${CARD} w-[356px] shrink-0 p-5`}>
          <h3 className="text-[13.5px] font-black">📦 产品原图</h3>
          <div className="mt-2 flex gap-2.5">
            <img src={PREVIEW_UPLOAD} alt="" className="size-[70px] rounded-[14px] border-2 border-[#ffe3d8] object-cover" />
            <div className="grid size-[70px] place-items-center rounded-[14px] border-2 border-dashed border-[#ffd2c2] bg-[#fff8f5] text-[22px] text-[#ffab92]">
              +
            </div>
          </div>

          <h3 className="mt-4 text-[13.5px] font-black">⚙️ 生成设置</h3>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {PREVIEW_MODIFIERS.map((m) => (
              <div key={m.label} className="rounded-[12px] bg-[#f7f1ff] px-2.5 py-2">
                <div className="text-[10px] font-bold text-[#9b8aa8]">{m.label}</div>
                <div className="mt-0.5 truncate text-[12px] font-black text-[#5b3b86]">{m.value}</div>
              </div>
            ))}
          </div>

          <div className="mt-4 flex items-center justify-between">
            <h3 className="text-[13.5px] font-black">🧺 套图结构</h3>
            <span className="rounded-full bg-[#ffe9f0] px-2.5 py-0.5 text-[11.5px] font-black text-[#ff5d7e]">
              5 张 · 约 ¥2.00
            </span>
          </div>
          <div className="mt-2 space-y-2">
            {PREVIEW_PLAN.map((p) => (
              <div key={p.label} className="flex items-center justify-between rounded-[14px] bg-[#fff6f2] px-3 py-2">
                <div className="text-[12.5px] font-bold">
                  {p.label}
                  <span className="ml-1.5 text-[10.5px] font-semibold text-[#c2a8b4]">{p.desc}</span>
                </div>
                <div className="flex items-center gap-2">
                  <button className="grid size-6 place-items-center rounded-full bg-white text-[13px] font-black text-[#ff5d7e] shadow-sm">−</button>
                  <span className="w-4 text-center text-[15px] font-black text-[#7c3aed]">{p.n}</span>
                  <button className="grid size-6 place-items-center rounded-full bg-white text-[13px] font-black text-[#ff5d7e] shadow-sm">＋</button>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {PREVIEW_OVERLAYS.map((t) => (
              <span key={t} className="rounded-full border-2 border-[#e9dcff] bg-[#f7f1ff] px-2.5 py-0.5 text-[11.5px] font-bold text-[#7c3aed]">
                {t} ✕
              </span>
            ))}
          </div>

          <h3 className="mt-4 text-[13.5px] font-black">💬 商品卖点 & 要求</h3>
          <p className="mt-2 rounded-[14px] bg-[#fff6f2] p-3 text-[12.5px] font-semibold leading-relaxed text-[#6b5560]">
            {PREVIEW_PROMPT}
          </p>

          <button
            className="relative mt-5 w-full overflow-hidden rounded-full py-3.5 text-[15px] font-black text-white shadow-[0_16px_34px_-12px_rgba(255,93,126,.65)]"
            style={{ background: GRAD }}
          >
            🚀 一键生成套图
            <span className="ml-2 rounded-full bg-white/25 px-2.5 py-0.5 text-[12.5px]">约 ¥2.00 · 5 张</span>
          </button>
          <p className="mt-2 text-center text-[11px] font-bold text-[#c2a8b4]">成功才计费 · 失败张不要钱 ✌️</p>
        </aside>

        {/* 结果区 */}
        <main className="flex-1">
          <div className={`${CARD} flex items-center justify-between px-5 py-3.5`}>
            <div className="flex items-center gap-3">
              <h1 className="text-[20px] font-black">商品套图</h1>
              <span className="rounded-full bg-[#e8fbef] px-2.5 py-0.5 text-[11.5px] font-black text-[#16a34a]">
                ✓ 5/5 全部完成
              </span>
              <span className="-rotate-2 rounded-[8px] bg-[#ff5d7e] px-2 py-0.5 text-[11px] font-black text-white">
                实付 ¥2.00
              </span>
            </div>
            <button className="rounded-full px-4 py-2 text-[12.5px] font-black text-white" style={{ background: GRAD }}>
              ⬇ 下载全部
            </button>
          </div>

          {PREVIEW_GROUPS.map((g) => (
            <section key={g.key} className="mt-4">
              <div className="mb-2.5 flex items-center gap-2">
                <span className="size-2.5 rounded-full" style={{ background: GRAD }} />
                <span className="text-[14.5px] font-black">{g.label}</span>
                <span className="rounded-full bg-white px-2 py-0.5 text-[10.5px] font-black text-[#9b8aa8] shadow-sm">
                  {g.count} 张
                </span>
              </div>
              <div className="flex gap-4">
                {PREVIEW_RESULTS.filter((r) => r.type === g.key).map((r) => (
                  <div key={r.no} className="w-[208px] overflow-hidden rounded-[20px] border-2 border-[#ffe3d8] bg-white shadow-[0_12px_28px_-16px_rgba(124,58,237,.3)]">
                    <img src={r.src} alt="" className="aspect-square w-full object-cover" />
                    <div className="flex items-center justify-between px-3 py-2">
                      <span className="text-[11px] font-black text-[#c2a8b4]">#{r.no}</span>
                      <div className="flex gap-1.5">
                        <button className="rounded-full bg-[#f7f1ff] px-2.5 py-1 text-[10.5px] font-black text-[#7c3aed]">下载</button>
                        <button className="rounded-full px-2.5 py-1 text-[10.5px] font-black text-white" style={{ background: GRAD }}>
                          再编辑
                        </button>
                      </div>
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
