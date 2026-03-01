<script setup lang="ts">

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const config = useRuntimeConfig()
const apiUrl = config.public.apiUrl as string

// ── API Keys tab ──────────────────────────────────────────────────────────────
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
    mistralKey.value = ''
    elevenLabsKey.value = ''
  } catch {}
}

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

// ── Screening tab ─────────────────────────────────────────────────────────────
const ENTITY_LABELS: Record<string, string> = {
  FACE: 'Face Detection',
  PERSON: 'Person Name',
  EMAIL_ADDRESS: 'Email Address',
  PHONE_NUMBER: 'Phone Number',
  LOCATION: 'Location',
  CREDIT_CARD: 'Credit Card',
  IBAN_CODE: 'IBAN',
  IP_ADDRESS: 'IP Address',
  US_SSN: 'US Social Security No.',
  US_PASSPORT: 'US Passport',
  US_BANK_NUMBER: 'US Bank Number',
  US_DRIVER_LICENSE: "US Driver's License",
  DATE_TIME: 'Date / Time',
  NRP: 'National/Religious/Political',
  URL: 'URL',
  MEDICAL_LICENSE: 'Medical License',
  CRYPTO: 'Crypto Address',
  UK_NHS: 'UK NHS Number',
}

const allEntities = ref<string[]>([])
const textEntities = ref<Set<string>>(new Set())
const imageEntities = ref<Set<string>>(new Set())
const audioEntities = ref<Set<string>>(new Set())
const savingEntities = ref(false)
const entitySaveMsg = ref('')

async function loadEntities() {
  try {
    const data = await $fetch<{
      all_entities: string[]
      entities: { text: string[]; image: string[]; audio: string[] }
    }>(`${apiUrl}/settings/entities`)
    allEntities.value = data.all_entities
    textEntities.value = new Set(data.entities.text)
    imageEntities.value = new Set(data.entities.image)
    audioEntities.value = new Set(data.entities.audio)
  } catch {}
}

function toggle(modality: 'text' | 'image' | 'audio', entity: string) {
  const refMap = { text: textEntities, image: imageEntities, audio: audioEntities }
  const r = refMap[modality]
  const s = new Set(r.value)
  s.has(entity) ? s.delete(entity) : s.add(entity)
  r.value = s
}

async function saveEntities() {
  savingEntities.value = true
  entitySaveMsg.value = ''
  try {
    await $fetch(`${apiUrl}/settings/entities`, {
      method: 'POST',
      body: {
        text: [...textEntities.value],
        image: [...imageEntities.value],
        audio: [...audioEntities.value],
      },
    })
    entitySaveMsg.value = 'Saved'
  } catch {
    entitySaveMsg.value = 'Error saving'
  } finally {
    savingEntities.value = false
  }
}

async function revertEntities() {
  try {
    const data = await $fetch<{ entities: { text: string[]; image: string[]; audio: string[] } }>(
      `${apiUrl}/settings/entities/reset`, { method: 'POST' }
    )
    textEntities.value = new Set(data.entities.text)
    imageEntities.value = new Set(data.entities.image)
    audioEntities.value = new Set(data.entities.audio)
    entitySaveMsg.value = 'Reverted to defaults'
  } catch {
    entitySaveMsg.value = 'Error reverting'
  }
}

watch(() => props.open, (v) => { if (v) { load(); loadEntities() } })

const tabs = [
  { label: 'API Keys', slot: 'api-keys' },
  { label: 'Screening Rules', slot: 'screening' },
]
</script>

<template>
  <UModal
    :open="open"
    @update:open="emit('update:open', $event)"
    title="Settings"
    :ui="{
      content: 'bg-white ring-1 ring-zinc-200 !w-[95vw] !max-w-[1100px]',
      header: 'border-b border-zinc-100',
      title: 'text-black font-semibold',
      footer: 'border-t border-zinc-100',
    }"
  >
    <template #body>
      <UTabs
        :items="tabs"
        color="neutral"
        class="w-full"
        :ui="{
          list: '!bg-black !rounded-none my-2.5',
          indicator: '!bg-white',
          trigger: '!text-white data-[state=active]:!text-black',
        }"
      >

        <!-- ── API Keys ── -->
        <template #api-keys>
          <div class="space-y-4 py-4">

            <!-- Mistral -->
            <div class="border border-zinc-200 bg-zinc-50 p-4 space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-sm font-semibold text-zinc-800">Mistral API Key</span>
                <UBadge v-if="hasMistralKey" color="success" variant="subtle" size="xs">Active</UBadge>
                <UBadge v-else color="error" variant="subtle" size="xs">Not set</UBadge>
              </div>
              <UInput v-model="mistralKey" type="password" placeholder="sk-…  (leave blank to keep existing)" class="font-mono text-sm w-full" />
            </div>

            <!-- ElevenLabs -->
            <div class="border border-zinc-200 bg-zinc-50 p-4 space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-sm font-semibold text-zinc-800">ElevenLabs API Key</span>
                <UBadge v-if="hasElevenLabsKey" color="success" variant="subtle" size="xs">Active</UBadge>
                <UBadge v-else color="error" variant="subtle" size="xs">Not set</UBadge>
              </div>
              <UInput v-model="elevenLabsKey" type="password" placeholder="(leave blank to keep existing)" class="font-mono text-sm w-full" />
            </div>

            <!-- Base URL -->
            <div class="border border-zinc-200 bg-zinc-50 p-4 space-y-2">
              <span class="text-sm font-semibold text-zinc-800">Mistral Base URL</span>
              <UInput v-model="mistralBaseUrl" placeholder="https://api.mistral.ai" class="font-mono text-sm w-full" />
            </div>

            <p class="text-xs text-zinc-400 px-1">
              Keys are saved to <code class="text-zinc-500 bg-zinc-100 px-1 py-0.5 rounded">backend/.env</code> and applied immediately — no restart needed.
            </p>

            <div class="flex items-center gap-3 pt-1">
              <UButton :loading="saving" @click="save" color="neutral" variant="ghost">Save</UButton>
              <span v-if="saveMsg" class="text-xs" :class="saveMsg.startsWith('Error') ? 'text-red-500' : 'text-green-600'">
                {{ saveMsg }}
              </span>
            </div>
          </div>
        </template>

        <!-- ── Screening Rules ── -->
        <template #screening>
          <div class="py-4 space-y-4">
            <div class="flex items-center gap-5">
              <p class="text-xs text-zinc-500">Select which PII types to detect and redact per modality. Changes apply immediately on the next request.</p>
              <div class="flex items-center gap-3 shrink-0 ml-auto">
                <span class="flex items-center gap-1.5 text-xs text-zinc-500">
                  <span class="w-3.5 h-3.5 border bg-black border-black shrink-0" />
                  Censored
                </span>
                <span class="flex items-center gap-1.5 text-xs text-zinc-500">
                  <span class="w-3.5 h-3.5 border bg-white border-zinc-400 shrink-0" />
                  Uncensored
                </span>
              </div>
            </div>

            <div class="grid grid-cols-3 gap-3">

              <!-- Text column -->
              <div class="border border-zinc-200 bg-zinc-50 p-4">
                <div class="flex items-center gap-2 mb-3 pb-2 border-b border-zinc-200">
                  <span class="w-2 h-2 rounded-full bg-black shrink-0"></span>
                  <span class="text-xs font-bold text-black uppercase tracking-wider">Text</span>
                  <span class="ml-auto text-xs text-zinc-400 whitespace-nowrap">{{ textEntities.size }} active</span>
                </div>
                <div class="space-y-2">
                  <label
                    v-for="e in allEntities.filter((e: string) => e !== 'FACE')" :key="`text-${e}`"
                    class="flex items-center gap-2.5 cursor-pointer select-none group"
                    @click="toggle('text', e)"
                  >
                    <span
                      class="w-3.5 h-3.5 border shrink-0 transition-colors"
                      :class="textEntities.has(e) ? 'bg-black border-black' : 'bg-white border-zinc-400'"
                    />
                    <span class="text-xs text-zinc-700 group-hover:text-black">{{ ENTITY_LABELS[e] ?? e }}</span>
                  </label>
                </div>
              </div>

              <!-- Image column -->
              <div class="border border-zinc-200 bg-zinc-50 p-4">
                <div class="flex items-center gap-2 mb-3 pb-2 border-b border-zinc-200">
                  <span class="w-2 h-2 rounded-full bg-black shrink-0"></span>
                  <span class="text-xs font-bold text-black uppercase tracking-wider">Image</span>
                  <span class="ml-auto text-xs text-zinc-400 whitespace-nowrap">{{ imageEntities.size }} active</span>
                </div>
                <div class="space-y-2">
                  <label
                    v-for="e in allEntities" :key="`image-${e}`"
                    class="flex items-center gap-2.5 cursor-pointer select-none group"
                    @click="toggle('image', e)"
                  >
                    <span
                      class="w-3.5 h-3.5 border shrink-0 transition-colors"
                      :class="imageEntities.has(e) ? 'bg-black border-black' : 'bg-white border-zinc-400'"
                    />
                    <span class="text-xs text-zinc-700 group-hover:text-black">{{ ENTITY_LABELS[e] ?? e }}</span>
                  </label>
                </div>
              </div>

              <!-- Audio column -->
              <div class="border border-zinc-200 bg-zinc-50 p-4">
                <div class="flex items-center gap-2 mb-3 pb-2 border-b border-zinc-200">
                  <span class="w-2 h-2 rounded-full bg-black shrink-0"></span>
                  <span class="text-xs font-bold text-black uppercase tracking-wider">Audio</span>
                  <span class="ml-auto text-xs text-zinc-400 whitespace-nowrap">{{ audioEntities.size }} active</span>
                </div>
                <div class="space-y-2">
                  <label
                    v-for="e in allEntities.filter((e: string) => e !== 'FACE')" :key="`audio-${e}`"
                    class="flex items-center gap-2.5 cursor-pointer select-none group"
                    @click="toggle('audio', e)"
                  >
                    <span
                      class="w-3.5 h-3.5 border shrink-0 transition-colors"
                      :class="audioEntities.has(e) ? 'bg-black border-black' : 'bg-white border-zinc-400'"
                    />
                    <span class="text-xs text-zinc-700 group-hover:text-black">{{ ENTITY_LABELS[e] ?? e }}</span>
                  </label>
                </div>
              </div>

            </div>

            <div class="flex items-center gap-3 pt-1">
              <UButton :loading="savingEntities" @click="saveEntities" color="neutral" variant="ghost">Save</UButton>
              <UButton @click="revertEntities" color="neutral" variant="ghost">Revert to defaults</UButton>
              <span v-if="entitySaveMsg" class="text-xs" :class="entitySaveMsg.startsWith('Error') ? 'text-red-500' : 'text-green-600'">
                {{ entitySaveMsg }}
              </span>
            </div>
          </div>
        </template>

      </UTabs>
    </template>

    <template #footer>
      <UButton variant="ghost" class="ml-auto" color="neutral" @click="emit('update:open', false)">
        Close
      </UButton>
    </template>
  </UModal>
</template>
