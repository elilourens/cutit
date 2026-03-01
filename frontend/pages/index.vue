<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const { latestSessions, connected } = useWebSocket()

useHead({ title: 'Cut It — Privacy-first AI Proxy' })

const settingsOpen = ref(false)
const selectedId = ref('')

// Always follow the newest session as it arrives
watch(
  () => latestSessions.value[0]?.id,
  (id: string | undefined) => { if (id) selectedId.value = id },
  { immediate: true },
)

const activeSession = computed(() =>
  latestSessions.value.find((s: { id: string }) => s.id === selectedId.value) ?? latestSessions.value[0] ?? null,
)

</script>

<template>
  <div class="flex flex-col h-screen bg-white text-black overflow-hidden">

    <!-- ── Top bar ──────────────────────────────────────────────────────── -->
    <header class="flex items-center gap-4 px-6 py-3 border-b border-zinc-200 shrink-0">
      <div class="flex items-center gap-2.5">
        <UIcon name="i-heroicons-scissors" class="w-4 h-4 text-black" />
        <span class="font-semibold text-sm tracking-tight">Cut It</span>
        <span class="text-zinc-400 text-xs">/ Privacy-first AI Proxy</span>
      </div>

      <div class="ml-auto flex items-center gap-3">
        <span class="flex items-center gap-1.5 px-2.5 py-1 bg-black text-white text-xs font-medium">
          <span class="w-1.5 h-1.5 bg-white" :class="connected ? 'animate-[pulse_2s_ease-in-out_infinite]' : 'opacity-40'" />
          {{ connected ? 'Connected' : 'Reconnecting' }}
        </span>

        <UButton icon="i-heroicons-cog-6-tooth" variant="ghost" color="neutral" size="sm" class="text-black" @click="settingsOpen = true" />
      </div>
    </header>

    <SettingsModal v-model:open="settingsOpen" />

    <!-- ── Scrollable content ────────────────────────────────────────────── -->
    <div class="flex-1 min-h-0 overflow-auto">
      <div class="px-6 py-5 space-y-4">

        <!-- Playground -->
        <Playground />

        <!-- Pipeline: single selected session -->
        <PipelineView :sessions="activeSession ? [activeSession] : []" />

        <!-- Session selector -->
        <div v-if="latestSessions.length" class="flex items-center gap-2 flex-wrap">
          <span class="text-xs text-zinc-400">Sessions:</span>
          <button
            v-for="(session, i) in latestSessions"
            :key="session.id"
            class="flex items-center gap-1.5 font-mono text-xs px-2.5 py-1 border transition-colors"
            :class="selectedId === session.id
              ? 'border-zinc-900 bg-zinc-900 text-white'
              : 'border-zinc-200 text-zinc-500 hover:border-zinc-400 hover:text-zinc-700'"
            @click="selectedId = session.id"
          >
            {{ session.id.slice(0, 8) }}
            <span
              class="text-[10px] font-medium px-1.5 py-0.5"
              :class="selectedId === session.id ? 'bg-white text-black' : 'bg-black text-white'"
            >{{ session.status }}</span>
            <span v-if="i === 0" class="text-[10px] opacity-60">latest</span>
          </button>
        </div>

      </div>

    </div>

  </div>
</template>
