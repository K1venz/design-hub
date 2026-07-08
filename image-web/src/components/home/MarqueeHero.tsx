import { motion, type Variants } from 'motion/react'

// Marquee Hero（hero-3 参考复刻）：纯白底 + 居中文字栈（胶囊 tagline → 超粗双行标题
// 逐词 reveal → muted 描述 → 圆角实色 CTA）+ 底部竖版图片无限走马灯（上下渐隐 mask、
// 匀速左移循环）。视觉参数照参考实测：卡 aspect-[3/4] h-48/md:h-64 rounded-2xl shadow-md、
// 轨道 gap-4、容器 h-1/3 md:h-2/5 + linear-gradient mask。技术栈换用项目现成 motion/react。

const containerV: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
}

const wordV: Variants = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
}

const fadeUpV: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' } },
}

export interface MarqueeHeroProps {
  tagline: string
  /** 标题行数组（每行独立换行；行内按空格拆词逐词 reveal，无空格的中文行整行 reveal）。 */
  titleLines: string[]
  description: string
  ctaText: string
  onCta: () => void
  /** 走马灯图片（竖版 3:4 裁切展示；数量不足会循环补齐）。 */
  images: string[]
}

const MARQUEE_MIN = 10

export function MarqueeHero({ tagline, titleLines, description, ctaText, onCta, images }: MarqueeHeroProps) {
  // 补齐到至少 MARQUEE_MIN 张，保证轨道长于视口、循环无缝。
  const strip: string[] = []
  while (strip.length < MARQUEE_MIN && images.length > 0) strip.push(...images)

  return (
    <section className="relative h-svh overflow-hidden bg-white text-neutral-950">
      {/* 文字栈：居中偏上（给底部走马灯留层），z 浮于图带之上 */}
      <motion.div
        variants={containerV}
        initial="hidden"
        animate="show"
        className="relative z-10 flex h-[62%] flex-col items-center justify-end px-4 text-center md:h-[58%]"
      >
        <motion.div
          variants={fadeUpV}
          className="mb-6 rounded-full border border-neutral-200 bg-white px-4 py-1.5 text-[13px] text-neutral-500 shadow-sm"
        >
          {tagline}
        </motion.div>

        <h1 className="text-5xl font-extrabold leading-[1.08] tracking-tight md:text-7xl lg:text-8xl">
          {titleLines.map((line, li) => (
            <span key={li} className="block">
              {(line.includes(' ') ? line.split(' ') : [line]).map((word, wi) => (
                <motion.span key={wi} variants={wordV} className="inline-block whitespace-pre">
                  {word}
                  {wi < line.split(' ').length - 1 ? ' ' : ''}
                </motion.span>
              ))}
            </span>
          ))}
        </h1>

        <motion.p
          variants={fadeUpV}
          className="mx-auto mt-6 max-w-xl text-[15px] leading-relaxed text-neutral-500 md:text-lg"
        >
          {description}
        </motion.p>

        <motion.button
          variants={fadeUpV}
          onClick={onCta}
          className="mt-8 rounded-full bg-red-500 px-8 py-3.5 text-[15px] font-bold text-white shadow-lg shadow-red-500/25 transition-transform hover:scale-105 active:scale-100"
        >
          {ctaText}
        </motion.button>
      </motion.div>

      {/* 底部无限走马灯：两份相同 group，x -50% 匀速循环=无缝；上下渐隐 mask 融入白底 */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.5 }}
        className="absolute bottom-0 left-0 h-1/3 w-full md:h-2/5 [mask-image:linear-gradient(to_bottom,transparent,black_20%,black_80%,transparent)]"
      >
        <motion.div
          className="flex h-full items-center"
          animate={{ x: ['0%', '-50%'] }}
          transition={{ duration: 38, ease: 'linear', repeat: Infinity }}
        >
          {[0, 1].map((g) => (
            <div key={g} className="flex shrink-0 gap-4 pr-4" aria-hidden={g === 1}>
              {strip.map((src, i) => (
                <div key={i} className="relative h-48 shrink-0 md:h-64" style={{ aspectRatio: '3 / 4' }}>
                  <img
                    src={src}
                    alt=""
                    loading={g === 0 && i < 6 ? 'eager' : 'lazy'}
                    className="size-full rounded-2xl object-cover shadow-md"
                  />
                </div>
              ))}
            </div>
          ))}
        </motion.div>
      </motion.div>
    </section>
  )
}
