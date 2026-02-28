<script setup lang="ts">
import type { SessionState } from '~/composables/useWebSocket'

const props = defineProps<{
  sessions: Record<string, SessionState>
}>()

const config = useRuntimeConfig()
const activeSessionId = ref<string | null>(null)

const sessionList = computed(() => Object.values(props.sessions))

const activeSession = computed(() =>
  activeSessionId.value ? props.sessions[activeSessionId.value] : sessionList.value[0],
)

const vaultEntries = computed(() => {
  const v = activeSession.value?.vault ?? {}
  return Object.entries(v).map(([fake, masked]) => ({ fake, real: masked }))
})

async function clearSession(sid: string) {
  await fetch(`${config.public.apiUrl}/vault/${sid}`, { method: 'DELETE' })
  delete props.sessions[sid]
  if (activeSessionId.value === sid) activeSessionId.value = null
}

function short(sid: string) {
  return sid.slice(0, 8)
}
</script>

<template>
  <div class="flex h-full bg-white">

    <!-- Session sidebar -->
    <div class="w-44 border-r border-zinc-200 overflow-y-auto shrink-0">
      <div class="px-3 py-2 text-[10px] font-semibold tracking-widest uppercase text-zinc-400">
        Sessions
      </div>
      <button
        v-for="session in sessionList"
        :key="session.id"
        class="w-full text-left px-3 py-2 flex items-center gap-2 transition-colors"
        :class="activeSession?.id === session.id ? 'opacity-100' : 'opacity-50'"
        @click="activeSessionId = session.id"
      >
        <UIcon name="i-heroicons-lock-closed" class="w-3 h-3 text-zinc-400 shrink-0" />
        <div class="min-w-0">
          <div class="font-mono text-xs text-zinc-800 truncate">{{ short(session.id) }}</div>
          <div class="text-[10px] text-zinc-400">{{ Object.keys(session.vault).length }} entries</div>
        </div>
      </button>
      <div v-if="sessionList.length === 0" class="px-3 py-4 text-xs text-zinc-400">
        No sessions yet
      </div>
    </div>

    <!-- Vault table -->
    <div class="flex-1 overflow-auto min-w-0">
      <div v-if="activeSession" class="h-full flex flex-col">
        <div class="flex items-center gap-2 px-4 py-2 border-b border-zinc-200 shrink-0">
          <span class="text-xs font-mono text-zinc-500">{{ short(activeSession.id) }}</span>
          <span class="text-zinc-300">·</span>
          <span class="text-xs text-zinc-400">{{ vaultEntries.length }} mappings</span>
          <div class="ml-auto">
            <UButton
              size="xs"
              color="error"
              variant="ghost"
              icon="i-heroicons-trash"
              @click="clearSession(activeSession.id)"
            >
              Clear
            </UButton>
          </div>
        </div>

        <div class="flex-1 overflow-auto">
          <table class="w-full text-xs font-mono">
            <thead class="sticky top-0 bg-white">
              <tr>
                <th class="text-left px-4 py-2 text-zinc-500 font-medium border-b border-zinc-200">
                  Fake (sent to cloud)
                </th>
                <th class="text-left px-4 py-2 text-zinc-500 font-medium border-b border-zinc-200">
                  Real (masked here)
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(entry, i) in vaultEntries"
                :key="i"
                class="border-b border-zinc-100"
              >
                <td class="px-4 py-2 text-zinc-800">{{ entry.fake }}</td>
                <td class="px-4 py-2 text-zinc-400 italic">{{ entry.real }}</td>
              </tr>
              <tr v-if="vaultEntries.length === 0">
                <td colspan="2" class="px-4 py-4 text-zinc-400 text-center">
                  No mappings yet — vault fills as PII is detected
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else class="flex items-center justify-center h-full text-zinc-400 text-xs">
        Select a session to inspect its vault
      </div>
    </div>
  </div>
</template>
