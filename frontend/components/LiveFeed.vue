<script setup lang="ts">
import type { WsEvent } from '~/composables/useWebSocket'

defineProps<{
  events: WsEvent[]
  connected: boolean
}>()

const EVENT_META: Record<string, { icon: string; color: 'primary' | 'success' | 'warning' | 'error' | 'info' | 'neutral'; label: string }> = {
  request_intercepted: { icon: 'i-heroicons-arrow-down-tray',    color: 'neutral', label: 'Intercepted' },
  screening_started:   { icon: 'i-heroicons-magnifying-glass',   color: 'warning', label: 'Screening'   },
  screening_done:      { icon: 'i-heroicons-shield-check',       color: 'success', label: 'Screened'    },
  vault_updated:       { icon: 'i-heroicons-lock-closed',        color: 'neutral', label: 'Vault'       },
  forwarding:          { icon: 'i-heroicons-arrow-up-tray',      color: 'neutral', label: 'Forwarding'  },
  response_received:   { icon: 'i-heroicons-arrow-down-circle',  color: 'neutral', label: 'Response'    },
  pipeline_snapshot:   { icon: 'i-heroicons-check-circle',       color: 'success', label: 'Done'        },
}

function meta(type: string) {
  return EVENT_META[type] ?? { icon: 'i-heroicons-information-circle', color: 'neutral', label: type }
}

function fmt(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function short(sid: string) {
  return sid ? sid.slice(0, 8) : ''
}
</script>

<template>
  <div class="flex flex-col h-full bg-white">
    <!-- Header -->
    <div class="flex items-center gap-2 px-4 py-3 border-b border-zinc-200">
      <span class="text-xs font-semibold tracking-widest uppercase text-zinc-500">Live Feed</span>
      <div class="ml-auto">
        <UBadge :color="connected ? 'success' : 'error'" variant="subtle" size="xs">
          {{ connected ? 'LIVE' : 'OFFLINE' }}
        </UBadge>
      </div>
    </div>

    <!-- Event list -->
    <div class="flex-1 overflow-y-auto px-2 py-2 space-y-0.5 font-mono text-xs">
      <TransitionGroup name="feed">
        <div
          v-for="(evt, i) in events"
          :key="`${evt.session_id}-${evt.timestamp}-${i}`"
          class="flex gap-2 items-start px-2 py-1.5 transition-colors"
        >
          <UIcon :name="meta(evt.type).icon" class="shrink-0 mt-0.5 w-3.5 h-3.5 text-zinc-400" />

          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5 mb-0.5">
              <UBadge :color="meta(evt.type).color" variant="subtle" size="xs">
                {{ meta(evt.type).label }}
              </UBadge>
              <span class="text-zinc-400">{{ short(evt.session_id) }}</span>
            </div>

            <div class="text-zinc-500 truncate">
              <template v-if="evt.type === 'request_intercepted'">
                {{ evt.data.method }} {{ evt.data.path }}
              </template>
              <template v-else-if="evt.type === 'screening_done'">
                {{ evt.data.findings_count }} PII items found
              </template>
              <template v-else-if="evt.type === 'vault_updated'">
                {{ (evt.data.fakes as string[])?.length ?? 0 }} mappings stored
              </template>
              <template v-else-if="evt.type === 'forwarding'">
                → {{ evt.data.target }}
              </template>
              <template v-else-if="evt.type === 'response_received'">
                HTTP {{ evt.data.status }} · {{ evt.data.bytes }}B
              </template>
            </div>

            <div class="text-zinc-300 mt-0.5">{{ fmt(evt.timestamp) }}</div>
          </div>
        </div>
      </TransitionGroup>

      <div v-if="events.length === 0" class="text-center text-zinc-400 py-10 text-xs">
        Waiting for traffic…
      </div>
    </div>
  </div>
</template>

<style scoped>
.feed-enter-active {
  transition: all 0.15s ease;
}
.feed-enter-from {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
