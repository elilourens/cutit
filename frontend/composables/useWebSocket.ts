export interface WsEvent {
  type: string
  timestamp: string
  session_id: string
  data: Record<string, unknown>
}

export interface Finding {
  entity_type: string
  start?: number
  end?: number
  value?: string
  fake?: string
  source?: string
  score?: number
}

export interface SessionState {
  id: string
  events: WsEvent[]
  original: string
  screened: string
  cloudResponse: string
  reconstructed: string
  originalImage: string | null
  screenedImage: string | null
  originalAudio: string | null
  screenedAudio: string | null
  redactedSegments: Array<{ start: number; end: number }>
  vault: Record<string, string>
  findings: Finding[]
  findingsCount: number
  status: 'intercepted' | 'screening' | 'forwarding' | 'done' | 'error'
}

export const useWebSocket = () => {
  const config = useRuntimeConfig()

  const events = ref<WsEvent[]>([])
  const sessions = ref<Record<string, SessionState>>({})
  const connected = ref(false)
  const ws = ref<WebSocket | null>(null)

  const latestSessions = computed(() =>
    Object.values(sessions.value)
      .sort((a, b) => (b.events[0]?.timestamp ?? '').localeCompare(a.events[0]?.timestamp ?? ''))
      .slice(0, 10),
  )

  function _ensureSession(sid: string): SessionState {
    if (!sessions.value[sid]) {
      sessions.value[sid] = {
        id: sid,
        events: [],
        original: '',
        screened: '',
        cloudResponse: '',
        reconstructed: '',
        originalImage: null,
        screenedImage: null,
        originalAudio: null,
        screenedAudio: null,
        redactedSegments: [],
        vault: {},
        findings: [],
        findingsCount: 0,
        status: 'intercepted',
      }
    }
    return sessions.value[sid]
  }

  function _handleEvent(evt: WsEvent) {
    // Prepend to global feed (newest first), cap at 200
    events.value.unshift(evt)
    if (events.value.length > 200) events.value.pop()

    const sid = evt.session_id
    if (!sid) return

    const session = _ensureSession(sid)
    session.events.push(evt)

    const d = evt.data as Record<string, string | number | string[]>

    switch (evt.type) {
      case 'request_intercepted':
        session.status = 'intercepted'
        break

      case 'screening_started':
        session.status = 'screening'
        break

      case 'screening_done':
        session.findingsCount = (d.findings_count as number) ?? 0
        session.findings = (d.findings as unknown as Finding[]) ?? []
        break

      case 'vault_updated':
        // fakes array — mask real values
        if (Array.isArray(d.fakes)) {
          const newVault: Record<string, string> = {}
          ;(d.fakes as string[]).forEach((f) => {
            newVault[f] = '●●●●●'
          })
          session.vault = newVault
        }
        break

      case 'forwarding':
        session.status = 'forwarding'
        break

      case 'response_received':
        session.status = 'done'
        break

      case 'pipeline_snapshot':
        session.original = (d.original as string) ?? ''
        session.screened = (d.screened as string) ?? ''
        session.cloudResponse = (d.cloud_response as string) ?? ''
        session.reconstructed = (d.reconstructed as string) ?? ''
        session.originalImage = (d.original_image as string) ?? null
        session.screenedImage = (d.screened_image as string) ?? null
        session.originalAudio = (d.original_audio as string) ?? null
        session.screenedAudio = (d.screened_audio as string) ?? null
        session.redactedSegments = (d.redacted_segments as unknown as Array<{ start: number; end: number }>) ?? []
        session.findingsCount = (d.findings as number) ?? session.findingsCount
        if (d.vault && typeof d.vault === 'object') {
          session.vault = d.vault as Record<string, string>
        }
        session.status = 'done'
        break
    }
  }

  function connect() {
    ws.value = new WebSocket(config.public.wsUrl as string)

    ws.value.onopen = () => {
      connected.value = true
    }

    ws.value.onmessage = (event: MessageEvent) => {
      try {
        const data: WsEvent = JSON.parse(event.data as string)
        _handleEvent(data)
      }
      catch {}
    }

    ws.value.onclose = () => {
      connected.value = false
      setTimeout(connect, 2000)
    }

    ws.value.onerror = () => {
      ws.value?.close()
    }
  }

  onMounted(connect)
  onUnmounted(() => ws.value?.close())

  return { events, sessions, latestSessions, connected }
}
