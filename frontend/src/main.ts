/**
 * 应用入口
 *
 * 装配顺序：Vue → Pinia（状态管理）→ Router（路由）→ 全局样式
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './style.css'
import 'vue-sonner/style.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
