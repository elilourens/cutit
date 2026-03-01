<template>
  <div class="mb-5 border border-zinc-200">
    <div class="flex items-center gap-2 px-4 py-3 border-b border-zinc-200">
      <UIcon name="i-heroicons-beaker" class="w-4 h-4 text-zinc-400" />
      <span class="font-semibold text-sm text-black">Playground</span>
      <span class="text-xs text-zinc-400">— send text, images, or audio through the screening pipeline</span>
    </div>

    <div class="space-y-3 p-4">
      <!-- Text input -->
      <UTextarea
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

      <!-- Transcription status -->
      <div v-if="transcribing" class="flex items-center gap-2 text-xs text-zinc-400">
        <UIcon name="i-heroicons-arrow-path" class="animate-spin w-3.5 h-3.5" />
        Transcribing audio…
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
          :disabled="sending"
          @click="fileInput?.click()"
        />

        <UButton
          :icon="recording ? 'i-heroicons-stop-circle' : 'i-heroicons-microphone'"
          size="sm"
          :color="recording ? 'error' : 'neutral'"
          variant="ghost"
          :class="recording ? '' : 'text-black'"
          :title="recording ? 'Stop recording' : 'Record audio'"
          :disabled="sending || transcribing"
          @click="toggleRecording"
        />

        <div class="flex-1" />

        <UButton
          label="Send through proxy"
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

const text = ref('')
const imageDataUrl = ref<string | null>(null)
const imageName = ref('')
const sending = ref(false)
const recording = ref(false)
const transcribing = ref(false)
const status = ref('')
const statusType = ref<'idle' | 'error' | 'success'>('idle')
const fileInput = ref<HTMLInputElement | null>(null)

let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []

const canSend = computed(() => (text.value.trim() || imageDataUrl.value) && !sending.value && !transcribing.value)

function setStatus(msg: string, type: 'idle' | 'error' | 'success' = 'idle') {
  status.value = msg
  statusType.value = type
}

function removeImage() {
  imageDataUrl.value = null
  imageName.value = ''
  if (fileInput.value) fileInput.value.value = ''
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

    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop())
      recording.value = false
      transcribing.value = true
      setStatus('')

      try {
        const blob = new Blob(audioChunks, { type: 'audio/webm' })
        const form = new FormData()
        form.append('file', blob, 'recording.webm')

        const res = await fetch(`${config.public.apiUrl}/playground/audio`, { method: 'POST', body: form })
        if (!res.ok) throw new Error(`Transcription failed: ${res.status}`)
        const { text: transcribed } = await res.json()

        if (transcribed) {
          text.value = text.value ? `${text.value}\n${transcribed}` : transcribed
        }
      } catch (err: any) {
        setStatus(err.message, 'error')
      } finally {
        transcribing.value = false
      }
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
  setStatus('Sending through proxy…')

  const content: any[] = []
  if (text.value.trim()) content.push({ type: 'text', text: text.value.trim() })
  if (imageDataUrl.value) content.push({ type: 'image_url', image_url: { url: imageDataUrl.value } })

  try {
    const res = await fetch(`${config.public.apiUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'mistral-small-latest',
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
