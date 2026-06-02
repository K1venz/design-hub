import fs from 'node:fs'
import path from 'node:path'
import type { Connect, Plugin } from 'vite'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 后端把出图/素材落成本地文件（file://），且暂无 HTTP 图床（见 ISSUE-0016）。
// 仅 **开发期** 加一个本地图床中间件：把后端 image-code 落点目录下的图按 HTTP 暴露，
// 让 dev 联调能看到真实 gpt-image 输出。生产仍依赖后端图床（前端零改动切换）。
const STORAGE_DIRS = ['generated', 'assets', 'exports'].map((d) =>
  path.resolve(import.meta.dirname, '../image-code', d),
)
const MIME: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
}

function devLocalImage(): Plugin {
  const handler: Connect.NextHandleFunction = (req, res) => {
    const raw = new URL(req.url ?? '', 'http://localhost').searchParams.get('p') ?? ''
    const resolved = path.resolve(decodeURIComponent(raw))
    const ext = path.extname(resolved).toLowerCase()
    const allowed = STORAGE_DIRS.some((dir) => resolved.startsWith(dir + path.sep))
    if (!allowed || !MIME[ext]) {
      res.statusCode = 403
      return res.end()
    }
    if (!fs.existsSync(resolved)) {
      res.statusCode = 404
      return res.end()
    }
    res.setHeader('Content-Type', MIME[ext])
    res.setHeader('Cache-Control', 'no-store')
    fs.createReadStream(resolved).pipe(res)
  }
  return {
    name: 'dev-local-image',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/__localimg', handler)
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), devLocalImage()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 3000,
    // Dev proxy: /api/* -> design_hub backend, strip the /api prefix.
    // Keeps the browser same-origin so the backend never needs CORS locally.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
