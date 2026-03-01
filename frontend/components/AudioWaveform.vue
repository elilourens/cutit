<script setup lang="ts">
interface RedactedSegment {
  start: number
  end: number
}

const props = defineProps<{
  src: string
  redactedSegments?: RedactedSegment[]
  showLegend?: boolean
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const playing = ref(false)
const duration = ref(0)

const NUM_BARS = 60

let audioCtx: AudioContext | null = null
let audioBuffer: AudioBuffer | null = null
let source: AudioBufferSourceNode | null = null
let playStartTime = 0
let playOffset = 0
let animFrame: number | null = null
let waveformData: number[] = []

function buildWaveform(buffer: AudioBuffer) {
  const raw = buffer.getChannelData(0)
  const step = Math.max(1, Math.floor(raw.length / NUM_BARS))
  const bars: number[] = []
  for (let i = 0; i < NUM_BARS; i++) {
    let sum = 0
    for (let j = 0; j < step; j++) {
      sum += Math.abs(raw[i * step + j] || 0)
    }
    bars.push(sum / step)
  }
  const max = Math.max(...bars, 0.001)
  waveformData = bars.map(b => b / max)
}

function barIsRedacted(barIdx: number): boolean {
  if (!props.redactedSegments?.length || !duration.value) return false
  const t0 = (barIdx / NUM_BARS) * duration.value
  const t1 = ((barIdx + 1) / NUM_BARS) * duration.value
  return props.redactedSegments.some(s => s.start < t1 && s.end > t0)
}

function draw(playFrac?: number) {
  const canvas = canvasRef.value
  if (!canvas || !waveformData.length) return
  const ctx = canvas.getContext('2d')!
  const W = canvas.width
  const H = canvas.height
  ctx.clearRect(0, 0, W, H)

  const slotW = W / NUM_BARS
  const barW = Math.max(1, slotW * 0.6)
  const midY = H / 2

  for (let i = 0; i < NUM_BARS; i++) {
    const x = i * slotW + (slotW - barW) / 2
    const h = Math.max(2, waveformData[i] * midY * 0.88)
    const played = playFrac !== undefined && i / NUM_BARS < playFrac
    const redacted = barIsRedacted(i)

    ctx.fillStyle = redacted
      ? (played ? '#18181b' : '#3f3f46')
      : '#d4d4d8'

    ctx.fillRect(x, midY - h, barW, h * 2)
  }

  // Playhead
  if (playFrac !== undefined && playFrac > 0 && playFrac < 1) {
    ctx.fillStyle = '#18181b'
    ctx.fillRect(Math.round(playFrac * W) - 1, 2, 2, H - 4)
  }
}

function tick() {
  if (!audioCtx || !duration.value) return
  const elapsed = playOffset + (audioCtx.currentTime - playStartTime)
  const frac = Math.min(elapsed / duration.value, 1)
  draw(frac)
  if (frac < 1 && playing.value) {
    animFrame = requestAnimationFrame(tick)
  } else if (frac >= 1) {
    playing.value = false
    playOffset = 0
    draw(0)
  }
}

function startSource(offset: number) {
  if (!audioCtx || !audioBuffer) return
  source = audioCtx.createBufferSource()
  source.buffer = audioBuffer
  source.connect(audioCtx.destination)
  source.start(0, offset)
  source.onended = () => {
    if (playing.value) {
      playing.value = false
      playOffset = 0
      draw()
    }
  }
}

async function togglePlay() {
  if (!audioCtx || !audioBuffer) return
  if (audioCtx.state === 'suspended') await audioCtx.resume()

  if (playing.value) {
    playOffset = playOffset + (audioCtx.currentTime - playStartTime)
    source?.stop()
    source = null
    playing.value = false
    if (animFrame) { cancelAnimationFrame(animFrame); animFrame = null }
    draw(playOffset / (duration.value || 1))
  } else {
    if (playOffset >= duration.value) playOffset = 0
    startSource(playOffset)
    playStartTime = audioCtx.currentTime
    playing.value = true
    animFrame = requestAnimationFrame(tick)
  }
}

async function loadAudio() {
  try {
    const res = await fetch(props.src)
    const ab = await res.arrayBuffer()
    audioCtx = new AudioContext()
    audioBuffer = await audioCtx.decodeAudioData(ab)
    duration.value = audioBuffer.duration
    buildWaveform(audioBuffer)
    await nextTick()
    const canvas = canvasRef.value
    if (canvas) {
      canvas.width = canvas.offsetWidth || 200
      canvas.height = 48
    }
    draw()
  } catch (e) {
    console.error('AudioWaveform: failed to load', e)
  }
}

onMounted(() => {
  if (props.src) loadAudio()
})

onUnmounted(() => {
  if (animFrame) cancelAnimationFrame(animFrame)
  try { source?.stop() } catch {}
  audioCtx?.close()
})
</script>

<template>
  <div class="space-y-1.5">
    <div class="flex items-center gap-2">
      <button
        class="shrink-0 w-6 h-6 border border-zinc-200 flex items-center justify-center hover:bg-zinc-50 transition-colors"
        @click="togglePlay"
      >
        <UIcon
          :name="playing ? 'i-heroicons-pause-solid' : 'i-heroicons-play-solid'"
          class="w-3 h-3 text-zinc-700"
        />
      </button>
      <canvas
        ref="canvasRef"
        class="flex-1 min-w-0 block"
        style="height: 48px; width: 100%"
      />
    </div>
    <div v-if="redactedSegments?.length && showLegend !== false" class="flex items-center gap-1.5 pl-8">
      <span class="inline-block w-2 h-2 bg-zinc-700 shrink-0" />
      <span class="text-[10px] text-zinc-400">redacted</span>
    </div>
  </div>
</template>
