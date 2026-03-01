<script setup lang="ts">
import type { SessionState, Finding } from '~/composables/useWebSocket'

defineProps<{
  sessions: SessionState[]
}>()

const STATUS_COLOR: Record<string, 'neutral' | 'warning' | 'success' | 'error'> = {
  intercepted: 'neutral',
  screening:   'warning',
  forwarding:  'neutral',
  done:        'success',
  error:       'error',
}

function short(sid: string) {
  return sid.slice(0, 8)
}

interface Segment {
  text: string
  highlighted: boolean
  entity_type?: string
}

function highlightText(text: string, findings: Finding[]): Segment[] {
  if (!text) return []

  // Collect spans: exact positions for Presidio, text-search for Ollama
  const allSpans: { start: number; end: number; entity_type: string }[] = []

  for (const f of findings ?? []) {
    if (f.start !== undefined && f.end !== undefined && f.end > f.start) {
      allSpans.push({ start: f.start, end: f.end, entity_type: f.entity_type })
    }
    else if (f.value) {
      let idx = text.indexOf(f.value)
      while (idx !== -1) {
        allSpans.push({ start: idx, end: idx + f.value.length, entity_type: f.entity_type })
        idx = text.indexOf(f.value, idx + f.value.length)
      }
    }
  }

  const sorted = allSpans.sort((a, b) => a.start - b.start)
  if (!sorted.length) return [{ text, highlighted: false }]

  const segments: Segment[] = []
  let cursor = 0

  for (const span of sorted) {
    if (span.start < cursor) continue
    if (span.start > cursor) segments.push({ text: text.slice(cursor, span.start), highlighted: false })
    segments.push({ text: text.slice(span.start, span.end), highlighted: true, entity_type: span.entity_type })
    cursor = span.end
  }

  if (cursor < text.length) segments.push({ text: text.slice(cursor), highlighted: false })

  return segments
}
</script>

<template>
  <div class="space-y-8">

    <!-- Empty state -->
    <div v-if="sessions.length === 0" class="flex items-center justify-center py-16">
      <div class="text-center">
        <UIcon name="i-heroicons-shield-check" class="w-10 h-10 text-zinc-200 mx-auto mb-3" />
        <p class="text-zinc-500 text-sm">No requests intercepted yet.</p>
        <p class="text-zinc-400 text-xs mt-1">
          Type a message above and click <strong>Send through proxy</strong>.
        </p>
      </div>
    </div>

    <!-- One block per session, newest first -->
    <div v-for="session in sessions" :key="session.id" class="border border-zinc-200">

      <!-- Session header -->
      <div class="flex items-center gap-2 px-4 py-2 border-b border-zinc-200">
        <span class="font-mono text-xs text-zinc-400">{{ short(session.id) }}</span>
        <UBadge :color="STATUS_COLOR[session.status] ?? 'neutral'" variant="subtle" size="xs">
          {{ session.status }}
        </UBadge>
        <span v-if="session.findingsCount > 0" class="text-xs text-zinc-500">
          · {{ session.findingsCount }} PII item{{ session.findingsCount !== 1 ? 's' : '' }} redacted
        </span>
      </div>

      <!-- 5-step grid -->
      <div class="grid grid-cols-5 divide-x divide-zinc-200">

        <!-- Step 1: Original -->
        <div class="p-4 space-y-3">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-black">Original</span>
            <UBadge color="success" variant="subtle" size="xs">LOCAL</UBadge>
          </div>
          <img
            v-if="session.originalImage"
            :src="session.originalImage"
            class="w-full border border-zinc-200 object-contain max-h-40"
            alt="original image"
          />
          <p v-if="session.original" class="font-mono text-xs text-zinc-700 whitespace-pre-wrap break-words leading-relaxed">{{ session.original }}</p>
          <p v-if="!session.original && !session.originalImage" class="text-xs text-zinc-300">—</p>
        </div>

        <!-- Step 2: Flagged -->
        <div class="p-4 space-y-3">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-black">Flagged</span>
            <UBadge color="warning" variant="subtle" size="xs">LOCAL</UBadge>
          </div>
          <p v-if="session.original" class="font-mono text-xs whitespace-pre-wrap break-words leading-relaxed">
            <template v-for="(seg, i) in highlightText(session.original, session.findings)" :key="i">
              <span
                v-if="seg.highlighted"
                :title="seg.entity_type"
                class="bg-amber-100 text-amber-800 px-0.5 cursor-help"
              >{{ seg.text }}</span>
              <span v-else class="text-zinc-700">{{ seg.text }}</span>
            </template>
          </p>
          <p v-if="!session.original" class="text-xs text-zinc-300">—</p>
          <div v-if="session.findings.length" class="text-[10px] space-y-0.5 pt-1 border-t border-zinc-100">
            <div v-for="(f, i) in session.findings" :key="i" class="flex items-center gap-1 flex-wrap">
              <span class="text-amber-600 font-medium">{{ f.entity_type }}</span>
              <span class="text-zinc-300">→</span>
              <span class="font-mono text-zinc-500">{{ f.fake }}</span>
            </div>
          </div>
        </div>

        <!-- Step 3: Censored -->
        <div class="p-4 space-y-3">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-black">Censored</span>
            <UBadge color="success" variant="subtle" size="xs">LOCAL</UBadge>
          </div>
          <img
            v-if="session.screenedImage"
            :src="session.screenedImage"
            class="w-full border border-zinc-200 object-contain max-h-40"
            alt="censored image"
          />
          <p v-if="session.screened" class="font-mono text-xs text-zinc-700 whitespace-pre-wrap break-words leading-relaxed">{{ session.screened }}</p>
          <p v-if="!session.screened && !session.screenedImage" class="text-xs text-zinc-300">—</p>
          <p v-if="session.findingsCount > 0" class="text-[10px] text-zinc-400 pt-1 border-t border-zinc-100">
            {{ session.findingsCount }} value(s) replaced with fakes
          </p>
        </div>

        <!-- Step 3: Cloud Response -->
        <div class="p-4 space-y-3">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-black">Cloud Response</span>
            <UBadge color="error" variant="subtle" size="xs">CLOUD</UBadge>
          </div>
          <p v-if="session.cloudResponse" class="font-mono text-xs text-zinc-700 whitespace-pre-wrap break-words leading-relaxed">{{ session.cloudResponse }}</p>
          <p v-else class="text-xs text-zinc-300">—</p>
        </div>

        <!-- Step 4: Reconstructed -->
        <div class="p-4 space-y-3">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-black">Reconstructed</span>
            <UBadge color="success" variant="subtle" size="xs">LOCAL</UBadge>
          </div>
          <p v-if="session.reconstructed" class="font-mono text-xs text-zinc-700 whitespace-pre-wrap break-words leading-relaxed">{{ session.reconstructed }}</p>
          <p v-else class="text-xs text-zinc-300">—</p>
          <p v-if="session.findingsCount > 0" class="text-[10px] text-zinc-400 pt-1 border-t border-zinc-100">
            Fakes swapped back to real values
          </p>
        </div>

      </div>
    </div>

  </div>
</template>
