import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// design/04 §7：build 产物输出到 web_server/static/（dist 提交 git，部署侧免 Node）
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
    // terser 比 esbuild 再省 5-8% gzip（04 §6 首屏 <200KB 预算）
    minify: 'terser',
    terserOptions: {
      compress: { passes: 2 },
    },
  },
  server: {
    proxy: {
      // 开发时代理 /api 到本机 web 服务（design/04 §7）
      '/api': 'http://127.0.0.1:8080',
    },
  },
})
