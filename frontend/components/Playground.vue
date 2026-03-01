<template>
  <div class="mb-5 border border-zinc-200">
    <div class="flex items-center gap-2 px-4 py-3 border-b border-zinc-200">
      <UIcon name="i-heroicons-beaker" class="w-4 h-4 text-zinc-400" />
      <span class="font-semibold text-sm text-black">Testing Playground</span>
      <span class="text-xs text-zinc-400">— send text, images, or audio through the screening pipeline</span>
    </div>

    <div class="space-y-3 p-4">

      <!-- Provider + model selector (hidden in audio mode) -->
      <div v-if="!audioBlob" class="flex items-center gap-2">
        <!-- Provider -->
        <div class="flex items-center gap-2 border border-zinc-200 bg-zinc-50 px-3 py-1.5 shrink-0">
          <span class="text-xs font-medium text-zinc-500 shrink-0">Provider</span>
          <select
            v-model="selectedProvider"
            class="text-xs font-semibold bg-transparent border-none outline-none text-black cursor-pointer"
            @change="onProviderChange"
          >
            <option v-for="p in PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
        </div>

        <!-- Model preset dropdown -->
        <div class="flex items-center gap-2 border border-zinc-200 bg-zinc-50 px-3 py-1.5 flex-1">
          <span class="text-xs font-medium text-zinc-500 shrink-0">Model</span>
          <select
            v-model="model"
            class="text-xs font-mono font-semibold bg-transparent border-none outline-none text-black cursor-pointer flex-1 min-w-0"
          >
            <option v-for="m in currentModels" :key="m" :value="m">{{ m }}</option>
            <option value="__custom__">Custom…</option>
          </select>
        </div>

        <!-- Custom model text input (shown when "Custom…" selected) -->
        <div v-if="model === '__custom__'" class="flex items-center gap-2 border border-zinc-900 bg-white px-3 py-1.5 flex-1">
          <span class="text-xs font-medium text-zinc-500 shrink-0">Custom</span>
          <input
            v-model="customModel"
            class="text-xs font-mono text-black bg-transparent border-none outline-none flex-1 min-w-0"
            placeholder="e.g. gpt-4o"
            autofocus
          />
        </div>
      </div>

      <!-- Text input (hidden in audio mode) -->
      <UTextarea
        v-if="!audioBlob"
        v-model="text"
        placeholder="Type a message… (try including a name, email, or phone number)"
        :rows="3"
        class="w-full font-mono text-sm"
      />

      <!-- Image preview -->
      <div v-if="imageDataUrl" class="flex items-start gap-3 p-3 border border-zinc-200">
        <img :src="imageDataUrl" class="h-14 w-14 object-cover border border-zinc-200" alt="attached image" />
        <div class="flex-1 min-w-0">
          <p class="text-xs text-zinc-600 truncate font-mono">{{ imageName }}</p>
          <p class="text-xs text-zinc-400 mt-0.5">Will be screened for visual PII before sending</p>
        </div>
        <UButton icon="i-heroicons-x-mark" size="xs" color="neutral" variant="ghost" class="text-black" @click="removeImage" />
      </div>

      <!-- Audio attachment preview -->
      <div v-if="audioBlob" class="flex items-center gap-3 p-3 border border-zinc-200 bg-zinc-50">
        <UIcon name="i-heroicons-speaker-wave" class="w-5 h-5 text-zinc-400 shrink-0" />
        <div class="flex-1 min-w-0">
          <p class="text-xs font-semibold text-zinc-700 font-mono">recording.webm</p>
          <p class="text-xs text-zinc-400 mt-0.5">Whisper will screen for PII → bleep → ElevenLabs STT</p>
        </div>
        <UButton icon="i-heroicons-x-mark" size="xs" color="neutral" variant="ghost" class="text-black" @click="removeAudio" />
      </div>

      <!-- Actions row -->
      <div class="flex items-center gap-2">
        <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onImageSelected" />

        <UButton
          icon="i-heroicons-paper-clip"
          size="sm"
          color="neutral"
          variant="ghost"
          class="text-black"
          title="Attach image"
          :disabled="sending || !!audioBlob"
          @click="fileInput?.click()"
        />

        <UButton
          :icon="recording ? 'i-heroicons-stop-circle' : 'i-heroicons-microphone'"
          size="sm"
          :color="recording ? 'error' : 'neutral'"
          variant="ghost"
          :class="recording ? '' : 'text-black'"
          :title="recording ? 'Stop recording' : 'Record audio for ElevenLabs'"
          :disabled="sending"
          @click="toggleRecording"
        />

        <div class="flex-1" />

        <UButton
          :label="audioBlob ? 'Screen + send to ElevenLabs' : 'Send through proxy'"
          icon="i-heroicons-paper-airplane"
          size="sm"
          color="neutral"
          variant="ghost"
          class="text-black"
          :loading="sending"
          :disabled="!canSend"
          @click="send"
        />
      </div>

      <!-- Status -->
      <div v-if="status">
        <UAlert
          v-if="statusType === 'error'"
          color="error"
          variant="subtle"
          :description="status"
          icon="i-heroicons-exclamation-triangle"
          size="sm"
        />
        <UAlert
          v-else-if="statusType === 'success'"
          color="success"
          variant="subtle"
          :description="status"
          icon="i-heroicons-check-circle"
          size="sm"
        />
        <p v-else class="text-xs text-zinc-400">{{ status }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const config = useRuntimeConfig()

const PROVIDERS = [
  {
    id: 'mistral', label: 'Mistral',
    models: [
      'mistral-large-latest',       // Mistral Large 3 — flagship
      'mistral-medium-latest',      // Mistral Medium 3
      'mistral-small-latest',       // Small 3.1 — fast & cheap
      'codestral-latest',           // Code completion
      'magistral-medium-2507',      // Reasoning (chain-of-thought)
      'ministral-8b-2512',          // Edge-friendly 8B
    ],
  },
  {
    id: 'openai', label: 'OpenAI',
    models: [
      'gpt-4o',                     // GPT-4o flagship
      'gpt-4o-mini',                // Fast & cheap
      'o3',                         // Reasoning flagship
      'o3-mini',                    // Fast reasoning
      'gpt-4.1-2025-04-14',        // 1M context window
      'gpt-4.1-mini-2025-04-14',   // Smaller 4.1
    ],
  },



]

const selectedProvider = ref('mistral')
const model = ref('mistral-small-latest')
const customModel = ref('')

const currentModels = computed(() =>
  PROVIDERS.find(p => p.id === selectedProvider.value)?.models ?? []
)

// The actual model string sent to the API
const resolvedModel = computed(() =>
  model.value === '__custom__' ? customModel.value.trim() : model.value
)

function onProviderChange() {
  const p = PROVIDERS.find(p => p.id === selectedProvider.value)
  if (p) model.value = p.models[0]
  customModel.value = ''
}

const text = ref('')
const imageDataUrl = ref<string | null>(null)
const imageName = ref('')
const audioBlob = ref<Blob | null>(null)
const sending = ref(false)
const recording = ref(false)
const status = ref('')
const statusType = ref<'idle' | 'error' | 'success'>('idle')
const fileInput = ref<HTMLInputElement | null>(null)

let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []

const canSend = computed(() => {
  if (sending.value) return false
  if (audioBlob.value) return true
  return (text.value.trim() || imageDataUrl.value) && resolvedModel.value.length > 0
})

function setStatus(msg: string, type: 'idle' | 'error' | 'success' = 'idle') {
  status.value = msg
  statusType.value = type
}

function removeImage() {
  imageDataUrl.value = null
  imageName.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

function removeAudio() {
  audioBlob.value = null
  setStatus('')
}

function onImageSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  imageName.value = file.name
  const reader = new FileReader()
  reader.onload = () => { imageDataUrl.value = reader.result as string }
  reader.readAsDataURL(file)
}

async function toggleRecording() {
  if (recording.value) {
    mediaRecorder?.stop()
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    audioChunks = []
    mediaRecorder = new MediaRecorder(stream)

    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data) }

    mediaRecorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop())
      recording.value = false
      audioBlob.value = new Blob(audioChunks, { type: 'audio/webm' })
      setStatus('Audio ready — click "Screen + send to ElevenLabs" to process')
    }

    mediaRecorder.start()
    recording.value = true
    setStatus('Recording… click stop when done')
  } catch (err: any) {
    setStatus(err.message, 'error')
  }
}

async function send() {
  sending.value = true

  // ── Audio mode: screen PII → bleep → ElevenLabs STT ──────────────────
  if (audioBlob.value) {
    setStatus('Screening audio for PII and sending to ElevenLabs…')
    try {
      const form = new FormData()
      form.append('file', audioBlob.value, 'recording.webm')

      const res = await fetch(`${config.public.apiUrl}/playground/audio/elevenlabs`, {
        method: 'POST',
        body: form,
      })

      if (!res.ok) {
        const body = await res.text()
        throw new Error(`${res.status} — ${body.slice(0, 200)}`)
      }

      const { text: transcript, findings } = await res.json()
      const piiNote = findings.length > 0
        ? ` (${findings.length} PII finding${findings.length !== 1 ? 's' : ''} bleeped)`
        : ''
      setStatus(`ElevenLabs transcript: "${transcript}"${piiNote}`, 'success')
      removeAudio()
    } catch (err: any) {
      setStatus(err.message, 'error')
    } finally {
      sending.value = false
    }
    return
  }

  // ── Text / image mode: existing chat completion flow ──────────────────
  setStatus('Sending through proxy…')

  const content: any[] = []
  if (text.value.trim()) content.push({ type: 'text', text: text.value.trim() })
  if (imageDataUrl.value) content.push({ type: 'image_url', image_url: { url: imageDataUrl.value } })

  try {
    const res = await fetch(`${config.public.apiUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: resolvedModel.value,
        messages: [{ role: 'user', content }],
      }),
    })

    if (!res.ok) {
      const body = await res.text()
      throw new Error(`${res.status} — ${body.slice(0, 200)}`)
    }

    setStatus('Done — see the pipeline results below', 'success')
    text.value = ''
    removeImage()
  } catch (err: any) {
    setStatus(err.message, 'error')
  } finally {
    sending.value = false
  }
}
</script>
