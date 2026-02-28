<script setup lang="ts">
const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const config = useRuntimeConfig()
const apiUrl = config.public.apiUrl as string

const mistralKey = ref('')
const elevenLabsKey = ref('')
const mistralBaseUrl = ref('')
const hasMistralKey = ref(false)
const hasElevenLabsKey = ref(false)
const saving = ref(false)
const saveMsg = ref('')

async function load() {
  try {
    const data = await $fetch<{
      mistral_api_key: string
      elevenlabs_api_key: string
      mistral_base_url: string
      has_mistral_key: boolean
      has_elevenlabs_key: boolean
    }>(`${apiUrl}/settings`)
    hasMistralKey.value = data.has_mistral_key
    hasElevenLabsKey.value = data.has_elevenlabs_key
    mistralBaseUrl.value = data.mistral_base_url
    // Don't pre-fill masked values into the inputs
    mistralKey.value = ''
    elevenLabsKey.value = ''
  } catch {}
}

watch(() => props.open, (v) => { if (v) load() })

async function save() {
  saving.value = true
  saveMsg.value = ''
  try {
    const body: Record<string, string> = {}
    if (mistralKey.value) body.mistral_api_key = mistralKey.value
    if (elevenLabsKey.value) body.elevenlabs_api_key = elevenLabsKey.value
    if (mistralBaseUrl.value) body.mistral_base_url = mistralBaseUrl.value

    await $fetch(`${apiUrl}/settings`, { method: 'POST', body })
    saveMsg.value = 'Saved — keys written to .env'
    await load()
  } catch {
    saveMsg.value = 'Error saving settings'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <UModal :open="open" @update:open="emit('update:open', $event)" title="API Keys">
    <template #body>
      <div class="space-y-5 py-2">

        <!-- Mistral -->
        <div class="space-y-1.5">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-black">Mistral API Key</span>
            <UBadge v-if="hasMistralKey" color="success" variant="subtle" size="xs">Set</UBadge>
            <UBadge v-else color="error" variant="subtle" size="xs">Not set</UBadge>
          </div>
          <UInput
            v-model="mistralKey"
            type="password"
            placeholder="sk-…  (leave blank to keep existing)"
            class="font-mono text-sm w-full"
          />
        </div>

        <!-- ElevenLabs -->
        <div class="space-y-1.5">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-black">ElevenLabs API Key</span>
            <UBadge v-if="hasElevenLabsKey" color="success" variant="subtle" size="xs">Set</UBadge>
            <UBadge v-else color="error" variant="subtle" size="xs">Not set</UBadge>
          </div>
          <UInput
            v-model="elevenLabsKey"
            type="password"
            placeholder="(leave blank to keep existing)"
            class="font-mono text-sm w-full"
          />
        </div>

        <!-- Mistral base URL -->
        <div class="space-y-1.5">
          <span class="text-sm font-medium text-black">Mistral Base URL</span>
          <UInput
            v-model="mistralBaseUrl"
            placeholder="https://api.mistral.ai"
            class="font-mono text-sm w-full"
          />
        </div>

        <p class="text-xs text-zinc-400">
          Keys are saved to <code class="text-zinc-600">backend/.env</code> and applied immediately — no restart needed.
        </p>
      </div>
    </template>

    <template #footer>
      <div class="flex items-center gap-3 w-full">
        <UButton :loading="saving" @click="save" color="neutral" class="shrink-0">
          Save
        </UButton>
        <span v-if="saveMsg" class="text-xs" :class="saveMsg.startsWith('Error') ? 'text-red-500' : 'text-green-600'">
          {{ saveMsg }}
        </span>
        <UButton variant="ghost" class="ml-auto" color="neutral" @click="emit('update:open', false)">
          Close
        </UButton>
      </div>
    </template>
  </UModal>
</template>
