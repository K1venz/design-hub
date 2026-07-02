import { useEffect, useRef, useState } from 'react'

/**
 * 首次进入视口即置 true（懒加载用）：观察目标 ref，命中后断开、不再翻转。
 * 无 IntersectionObserver 环境（SSR/测试）降级为直接可见（初值即 true）。
 */
export function useInView<T extends Element>(rootMargin = '120px'): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null)
  const [inView, setInView] = useState(() => typeof IntersectionObserver === 'undefined')

  useEffect(() => {
    const el = ref.current
    if (!el || inView || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setInView(true)
          io.disconnect()
        }
      },
      { rootMargin },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [inView, rootMargin])

  return [ref, inView]
}
