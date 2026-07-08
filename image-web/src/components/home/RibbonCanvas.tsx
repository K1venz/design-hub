import { useEffect, useRef } from 'react'

// 忠实移植用户参考件 canvas.tsx（Downloads/生图平台Hero页 提示词）：80 条弹簧丝带跟随
// 鼠标，色相振荡器 offset 285 ± 85 正弦流转，lighter 叠加 + 粗线(10px)极低透明度(0.025)
// 成柔和彩虹光带。参数 1:1：friction .5 / dampening .025 / tension .99 / size 50 /
// spring .45+i/80*.025 / 每帧全清。与原件行为一致：首次 mousemove/touchstart 才生成丝带
// 并启动渲染。改造仅工程化：TS class、React 挂卸全清监听、touchmove 改 passive 不劫持滚动。

const E = { trails: 80, size: 50, friction: 0.5, dampening: 0.025, tension: 0.99 } as const

/** 色相振荡器（原件 n()）：hue = offset + sin(phase) * amplitude。 */
class Oscillator {
  private phase: number
  private readonly offset: number
  private readonly frequency: number
  private readonly amplitude: number

  constructor(opts: { phase: number; offset: number; frequency: number; amplitude: number }) {
    this.phase = opts.phase
    this.offset = opts.offset
    this.frequency = opts.frequency
    this.amplitude = opts.amplitude
  }

  update(): number {
    this.phase += this.frequency
    return this.offset + Math.sin(this.phase) * this.amplitude
  }
}

interface NodePoint {
  x: number
  y: number
  vx: number
  vy: number
}

/** 弹簧丝带（原件 Line()）：头节点追鼠标，后续节点弹簧牵引 + 阻尼传导。 */
class Line {
  private readonly spring: number
  private readonly friction: number
  private readonly nodes: NodePoint[]

  constructor(spring: number, x: number, y: number) {
    this.spring = spring + 0.1 * Math.random() - 0.05
    this.friction = E.friction + 0.01 * Math.random() - 0.005
    this.nodes = Array.from({ length: E.size }, () => ({ x, y, vx: 0, vy: 0 }))
  }

  update(pos: { x: number; y: number }) {
    let spring = this.spring
    const head = this.nodes[0]
    head.vx += (pos.x - head.x) * spring
    head.vy += (pos.y - head.y) * spring
    for (let i = 0; i < this.nodes.length; i++) {
      const node = this.nodes[i]
      if (i > 0) {
        const prev = this.nodes[i - 1]
        node.vx += (prev.x - node.x) * spring
        node.vy += (prev.y - node.y) * spring
        node.vx += prev.vx * E.dampening
        node.vy += prev.vy * E.dampening
      }
      node.vx *= this.friction
      node.vy *= this.friction
      node.x += node.vx
      node.y += node.vy
      spring *= E.tension
    }
  }

  draw(ctx: CanvasRenderingContext2D) {
    let x = this.nodes[0].x
    let y = this.nodes[0].y
    ctx.beginPath()
    ctx.moveTo(x, y)
    let i = 1
    for (; i < this.nodes.length - 2; i++) {
      const a = this.nodes[i]
      const b = this.nodes[i + 1]
      x = 0.5 * (a.x + b.x)
      y = 0.5 * (a.y + b.y)
      ctx.quadraticCurveTo(a.x, a.y, x, y)
    }
    const a = this.nodes[i]
    const b = this.nodes[i + 1]
    ctx.quadraticCurveTo(a.x, a.y, b.x, b.y)
    ctx.stroke()
    ctx.closePath()
  }
}

export function RibbonCanvas({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let running = true
    let raf = 0
    const pos = { x: 0, y: 0 }
    let lines: Line[] = []
    const hue = new Oscillator({
      phase: Math.random() * 2 * Math.PI,
      offset: 285,
      frequency: 0.0015,
      amplitude: 85,
    })

    // 原件尺寸口径：width = innerWidth - 20（配合 demo 的 mx-auto 居中）。
    function resize() {
      canvas!.width = window.innerWidth - 20
      canvas!.height = window.innerHeight
    }

    function setPos(e: MouseEvent | TouchEvent) {
      if ('touches' in e) {
        pos.x = e.touches[0].pageX
        pos.y = e.touches[0].pageY
      } else {
        pos.x = e.clientX
        pos.y = e.clientY
      }
    }

    function onTouchStart(e: TouchEvent) {
      if (e.touches.length === 1) {
        pos.x = e.touches[0].pageX
        pos.y = e.touches[0].pageY
      }
    }

    function render() {
      if (!running) return
      ctx!.globalCompositeOperation = 'source-over'
      ctx!.clearRect(0, 0, canvas!.width, canvas!.height)
      ctx!.globalCompositeOperation = 'lighter'
      ctx!.strokeStyle = `hsla(${Math.round(hue.update())},100%,50%,0.025)`
      ctx!.lineWidth = 10
      for (const line of lines) {
        line.update(pos)
        line.draw(ctx!)
      }
      raf = requestAnimationFrame(render)
    }

    // 与原件一致：首次 mousemove/touchstart 定位后才生成丝带、启动渲染。
    function onFirstMove(e: MouseEvent | TouchEvent) {
      document.removeEventListener('mousemove', onFirstMove)
      document.removeEventListener('touchstart', onFirstMove)
      setPos(e)
      lines = Array.from(
        { length: E.trails },
        (_, i) => new Line(0.45 + (i / E.trails) * 0.025, pos.x, pos.y),
      )
      document.addEventListener('mousemove', setPos)
      document.addEventListener('touchmove', setPos, { passive: true })
      document.addEventListener('touchstart', onTouchStart, { passive: true })
      render()
    }

    resize()
    document.addEventListener('mousemove', onFirstMove)
    document.addEventListener('touchstart', onFirstMove)
    window.addEventListener('resize', resize)

    return () => {
      running = false
      cancelAnimationFrame(raf)
      document.removeEventListener('mousemove', onFirstMove)
      document.removeEventListener('touchstart', onFirstMove)
      document.removeEventListener('mousemove', setPos)
      document.removeEventListener('touchmove', setPos)
      document.removeEventListener('touchstart', onTouchStart)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return <canvas ref={canvasRef} aria-hidden className={className} />
}
