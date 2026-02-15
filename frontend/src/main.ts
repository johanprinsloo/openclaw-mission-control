import { createApp } from 'vue'
import { createPinia } from 'pinia'

// Vuetify
import 'vuetify/styles'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import '@mdi/font/css/materialdesignicons.css'

// Tailwind
import './style.css'

import App from './App.vue'
import router from './router'

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'mcLight',
    themes: {
      mcLight: {
        dark: false,
        colors: {
          background: '#F5F0E8',
          surface: '#FFFFFF',
          'surface-variant': '#EBE5DB',
          primary: '#C47830',
          secondary: '#3D7FCA',
          error: '#C0392B',
          success: '#5A9E6F',
          warning: '#D4742C',
          info: '#3D7FCA',
        },
      },
    },
  },
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(vuetify)
app.mount('#app')
