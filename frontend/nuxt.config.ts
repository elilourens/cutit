export default defineNuxtConfig({
  modules: ['@nuxt/ui'],

  css: ['~/assets/css/main.css'],

  devtools: { enabled: false },

  colorMode: {
    preference: 'light',
  },

  runtimeConfig: {
    public: {
      wsUrl: 'ws://localhost:8080/ws',
      apiUrl: 'http://localhost:8080',
    },
  },

  compatibilityDate: '2024-04-03',
})
