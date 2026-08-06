import { Fragment, useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  ArrowRightIcon,
  Loader2Icon,
  SparklesIcon,
  WandSparklesIcon,
} from 'lucide-react'

import { ChatComposer } from '@/components/chat/ChatComposer'
import type { ChatImageFileSelection } from '@/components/chat/chat-image-files'
import { ChatImagePreviewDialog } from '@/components/chat/ChatImagePreviewDialog'
import { ChatJobResult } from '@/components/chat/ChatJobResult'
import { SessionSidebar } from '@/components/chat/SessionSidebar'
import { ReversePromptDialog } from '@/components/image-tools/ReversePromptDialog'
import { AppShell } from '@/components/layout/AppShell'
import {
  requireSelectedImageModel,
  useImageModelSelection,
} from '@/components/models/image-model-context'
import { requireSelectedModel } from '@/components/models/model-selection'
import { useModelSelection } from '@/components/models/use-model-selection'
import { useChatModels } from '@/api/models'
import { CHAT_SESSIONS_KEY, confirmChat, getChatSession, sendChatMessage } from '@/api/chat'
import { listingJobQueryKey, useUploadImage } from '@/api/listing'
import {
  applyChatEvent, CHAT_WELCOME_COPY, clearAwaiting, consumeChatEditSource,
  initialChatState, pushUserMessage,
  sessionMessagesToBubbles, shouldShowChatWelcome,
  type ChatBubble, type ChatEditSource, type ChatPreviewImage, type ChatState,
  type ChatActionCard, type GenerationConfirm,
} from '@/lib/chat'
import {
  INITIAL_CHAT_IMAGE_OPTIONS,
  normalizeChatImageOptionsForModel,
  resolveChatImageOptions,
  type ChatImageOptionDraft,
} from '@/lib/chat-image-options'
import { decorateChatImageModelSelection } from '@/lib/chat-image-model-selection'
import type { ImageToolSource } from '@/lib/image-tools'
import type { UploadedImage } from '@/lib/listing'
import { uploadIdPreviewUrl, uploadPreviewUrl } from '@/lib/upload'
import { useAuthStore } from '@/stores/auth-store'

const PHASE_LABEL: Record<string, string> = {
  understood: '已理解需求',
  planning: '正在规划',
  generating: '正在出图',
  analyzing: '正在分析图片',
  done: '完成',
}

/**
 * 「帮我设计」对话页（登录内测，方案 C）。Hero/快捷卡带来的 `?q=` 自动发首条。
 * 流式气泡 + 步骤条 + 工具透明 + 生成确认 + 出图结果卡（job_event 复用工作台渲染）。
 */
export function ChatPage() {
  const [params] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const token = useAuthStore((auth) => auth.token)
  const imageModelSelection = useImageModelSelection()
  const chatModelsQuery = useChatModels()
  const chatModelSelection = useModelSelection('chat', chatModelsQuery)
  const [state, setState] = useState<ChatState>(initialChatState)
  const [draft, setDraft] = useState('')
  const [imageOptions, setImageOptions] = useState<ChatImageOptionDraft>(
    INITIAL_CHAT_IMAGE_OPTIONS,
  )
  const [attached, setAttached] = useState<UploadedImage[]>([])
  const [selectedEditSource, setSelectedEditSource] = useState<ChatEditSource | null>(null)
  const [previewImage, setPreviewImage] = useState<ChatPreviewImage | null>(null)
  const [reverseSource, setReverseSource] =
    useState<ImageToolSource | null>(null)
  const upload = useUploadImage()
  const qc = useQueryClient()
  const abortRef = useRef<AbortController | null>(null)
  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])
  const scrollRef = useRef<HTMLDivElement>(null)
  const pendingSeedRef = useRef<string | null>(null)
  const pendingSendRef = useRef<{
    state: ChatState
    draft: string
    attached: UploadedImage[]
    selectedEditSource: ChatEditSource | null
    imageOptions: ChatImageOptionDraft
  } | null>(null)
  const selectedImageModel =
    imageModelSelection.models.find(
      (model) => model.id === imageModelSelection.modelId,
    ) ?? null
  const hasReferences = attached.length > 0 || selectedEditSource !== null

  const on = (event: Parameters<typeof applyChatEvent>[1]) => {
    if (event.kind === 'job') {
      void qc.invalidateQueries({ queryKey: listingJobQueryKey(event.jobId) })
    }
    if (event.kind === 'error' && event.code === 'model_unavailable') {
      const pending = pendingSendRef.current
      if (pending) {
        setState({
          ...pending.state,
          error: { code: event.code, message: event.message },
        })
        setDraft(pending.draft)
        setAttached(pending.attached)
        setSelectedEditSource(pending.selectedEditSource)
        setImageOptions(pending.imageOptions)
        pendingSendRef.current = null
      } else {
        setState((current) => applyChatEvent(current, event))
      }
      imageModelSelection.retry()
      chatModelSelection.retry()
      toast.error('当前模型已不可用，内容已保留，请重新选择。')
      return
    }
    setState((current) => applyChatEvent(current, event))
  }

  // 一轮流结束后刷新会话列表（首轮新建会话入列、后续轮更新标题/时间/消息数）。
  const refreshSessions = () => qc.invalidateQueries({ queryKey: CHAT_SESSIONS_KEY })

  // 选中历史会话 → 拉转录还原成气泡（过程态不落库故为空；出图靠 job_id 现签重渲）。
  const loadSession = useMutation({
    mutationFn: getChatSession,
    onSuccess: (detail) =>
      setState({
        ...initialChatState(),
        sessionId: detail.id,
        bubbles: sessionMessagesToBubbles(detail.messages, (id) =>
          uploadIdPreviewUrl(id, token),
        ),
      }),
    onError: (e) => toast.error(e instanceof Error ? e.message : '加载会话失败'),
  })

  function selectSession(id: string) {
    if (id === stateRef.current.sessionId || loadSession.isPending) return
    abortRef.current?.abort()
    setSelectedEditSource(null)
    setImageOptions(INITIAL_CHAT_IMAGE_OPTIONS)
    setPreviewImage(null)
    setReverseSource(null)
    loadSession.mutate(id)
  }

  function newSession() {
    abortRef.current?.abort()
    loadSession.reset()
    setState(initialChatState())
    setDraft('')
    setAttached([])
    setSelectedEditSource(null)
    setPreviewImage(null)
    setReverseSource(null)
  }

  function selectEditSource(source: ChatEditSource) {
    if (stateRef.current.streaming || stateRef.current.awaiting) {
      toast.info('请等待当前对话完成后再继续编辑')
      return
    }
    if (selectedImageModel) {
      setImageOptions((current) =>
        normalizeChatImageOptionsForModel(current, selectedImageModel, true),
      )
    }
    setAttached([])
    setSelectedEditSource(source)
  }

  function openBackground(source: ChatEditSource) {
    navigate('/background', {
      state: {
        prefill: {
          source_kind: 'generated',
          source_id: source.imageKey,
          source_url: source.url,
        },
      },
    })
  }

  function openActionCard(action: ChatActionCard) {
    navigate('/background', { state: { prefill: action.prefill } })
  }

  function reverseGeneratedImage(source: ChatEditSource) {
    setReverseSource({
      kind: 'generated',
      imageKey: source.imageKey,
      previewUrl: source.url,
    })
  }

  async function send(message: string, uploadIds?: string[]) {
    const text = message.trim()
    if (
      !text ||
      stateRef.current.streaming ||
      stateRef.current.awaiting ||
      imageModelSelection.state !== 'ready' ||
      chatModelSelection.state !== 'ready' ||
      upload.isPending
    ) {
      return
    }
    const imageModel = requireSelectedImageModel(imageModelSelection)
    const chatModel = requireSelectedModel(chatModelSelection, '文本')
    if (!selectedImageModel) {
      throw new Error('图片模型目录与当前选择不一致')
    }
    const normalizedImageOptions = normalizeChatImageOptionsForModel(
      imageOptions,
      selectedImageModel,
      Boolean(uploadIds?.length || selectedEditSource),
    )
    const consumed = consumeChatEditSource(selectedEditSource)
    pendingSendRef.current = {
      state: stateRef.current,
      draft: text,
      attached,
      selectedEditSource,
      imageOptions: normalizedImageOptions,
    }
    setState((prev) =>
      pushUserMessage(
        prev,
        text,
        uploadIds && uploadIds.length
          ? attached.map((image) => uploadPreviewUrl(image.url, token))
          : undefined,
      ),
    )
    setDraft('')
    setAttached([])
    setSelectedEditSource(consumed.nextSelection)
    abortRef.current?.abort() // 中止上一条在途流（至多一条活跃）
    const ac = new AbortController()
    abortRef.current = ac
    try {
      await sendChatMessage({
        sessionId: stateRef.current.sessionId,
        message: text,
        chatModel,
        imageModel,
        imageOptions: resolveChatImageOptions(normalizedImageOptions),
        uploadIds,
        editSourceImageKey: consumed.editSourceImageKey,
      }, on, ac.signal)
      pendingSendRef.current = null
      refreshSessions()
    } catch (err) {
      pendingSendRef.current = null
      if (!ac.signal.aborted) {
        setState((prev) => ({ ...prev, streaming: false }))
        toast.error(err instanceof Error ? err.message : '对话请求失败')
      }
    }
  }

  async function resolveConfirm(
    action: 'confirm' | 'cancel',
    confirmation: GenerationConfirm,
  ) {
    const sid = stateRef.current.sessionId
    if (!sid) return
    setState((prev) => clearAwaiting(prev))
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    try {
      await confirmChat({
        sessionId: sid,
        confirmToken: confirmation.confirmToken,
        action,
      }, on, ac.signal)
      refreshSessions()
    } catch (err) {
      if (!ac.signal.aborted) {
        setState((prev) => ({ ...prev, streaming: false }))
        toast.error(err instanceof Error ? err.message : '确认请求失败')
      }
    }
  }

  // Hero/快捷卡首句先保留为可编辑草稿；目录 ready 后才自动发送。
  // 目录 error/empty/需重选时停止自动发送，避免用户修复目录后突然发出旧草稿。
  const seededRef = useRef(false)
  useEffect(() => {
    const stateSeed = (location.state as { q?: string } | null)?.q?.trim()
    const querySeed = params.get('q')?.trim()
    const seed = stateSeed || querySeed
    if (seed && !seededRef.current) {
      seededRef.current = true
      pendingSeedRef.current = seed
      setDraft(seed)
    }
    // 清 URL query（明文隐私）+ history state（防刷新重发）
    if (seed || location.state) navigate(location.pathname, { replace: true, state: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const seed = pendingSeedRef.current
    if (!seed) return
    const modelsReady =
      imageModelSelection.state === 'ready' &&
      chatModelSelection.state === 'ready'
    const catalogLoading =
      imageModelSelection.state === 'loading' ||
      chatModelSelection.state === 'loading'
    if (modelsReady) {
      pendingSeedRef.current = null
      void send(seed)
    } else if (!catalogLoading) {
      pendingSeedRef.current = null
    }
    // send intentionally uses the current composer snapshot when readiness changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatModelSelection.state, imageModelSelection.state])

  // 新内容滚到底
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [state.bubbles, state.awaiting])

  async function onPickFiles(files: readonly File[]) {
    if (files.length === 0) return
    setSelectedEditSource(null)
    for (const f of files) {
      try {
        const up = await upload.mutateAsync(f)
        if (selectedImageModel) {
          setImageOptions((current) =>
            normalizeChatImageOptionsForModel(current, selectedImageModel, true),
          )
        }
        setAttached((prev) => [...prev, up])
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '图片上传失败')
      }
    }
  }

  function onFileSelection(selection: ChatImageFileSelection) {
    if (selection.unsupportedCount > 0) {
      toast.error('仅支持 PNG、JPG、WebP 图片')
    }
    if (selection.full) {
      toast.info('最多添加 3 张图片，请先删除已有图片')
    } else if (selection.overflowCount > 0) {
      toast.info(`最多添加 3 张图片，${selection.overflowCount} 张未添加`)
    }
  }

  const busy = state.streaming || state.awaiting !== null
  const modelsReady =
    imageModelSelection.state === 'ready' &&
    chatModelSelection.state === 'ready'
  const composerImageModelSelection = decorateChatImageModelSelection(
    imageModelSelection,
    (model) => {
      setImageOptions((current) =>
        normalizeChatImageOptionsForModel(current, model, hasReferences),
      )
    },
  )

  return (
    <AppShell>
      <main className="flex min-h-0 flex-1 gap-3 overflow-hidden pb-3 pr-3">
        <SessionSidebar
          activeId={state.sessionId}
          loadingId={loadSession.isPending ? loadSession.variables ?? null : null}
          onSelect={selectSession}
          onNew={newSession}
        />
        <div className="mx-auto flex h-full min-w-0 max-w-3xl flex-1 flex-col">
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-auto px-2 py-4">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-wb-ink-2">
              <span className="grid size-7 place-items-center rounded-[9px] bg-gradient-to-br from-wb-grad-from to-wb-grad-to text-white">
                <WandSparklesIcon className="size-4" />
              </span>
              帮我设计
              <span className="rounded-full bg-wb-tint-1 px-2 py-0.5 text-[11px] font-medium text-wb-brand-deep">内测</span>
            </div>

            {shouldShowChatWelcome(state) && (
              <div className="flex items-start gap-2 pt-4">
                <span className="mt-1 grid size-7 shrink-0 place-items-center rounded-[9px] bg-wb-tint-1 text-wb-brand-deep">
                  <SparklesIcon className="size-4" />
                </span>
                <div className="max-w-[88%] rounded-2xl rounded-tl-md border border-white/80 bg-white/85 px-4 py-3 text-[14px] leading-7 text-wb-ink-3 shadow-[0_10px_30px_-20px_rgba(40,40,90,.35)]">
                  {CHAT_WELCOME_COPY}
                </div>
              </div>
            )}

            {state.bubbles.map((b, i) => (
              <Fragment key={i}>
                <Bubble
                  bubble={b}
                  awaiting={state.awaiting}
                  onResolve={resolveConfirm}
                  onOpenAction={openActionCard}
                />
                {b.jobId && (
                  <ChatJobResult
                    jobId={b.jobId}
                    onPreview={setPreviewImage}
                    onEdit={selectEditSource}
                    onBackground={openBackground}
                    onReversePrompt={reverseGeneratedImage}
                  />
                )}
              </Fragment>
            ))}

            {state.streaming && !state.awaiting && (
              <div className="flex items-center gap-2 px-1 text-[12.5px] text-wb-ink-6">
                <Loader2Icon className="size-3.5 animate-spin" /> 思考中…
              </div>
            )}

            {state.error && (
              <div className="rounded-xl border border-wb-red-line bg-wb-red-tint px-3 py-2 text-[12.5px] text-wb-red">
                {state.error.message}
              </div>
            )}
          </div>

          <ChatComposer
            draft={draft}
            onDraftChange={(value) => {
              pendingSeedRef.current = null
              setDraft(value)
            }}
            attached={attached}
            selectedEditSource={selectedEditSource}
            token={token}
            busy={busy}
            modelsReady={modelsReady}
            uploadPending={upload.isPending}
            imageOptions={imageOptions}
            onImageOptionsChange={setImageOptions}
            chatSelection={chatModelSelection}
            imageSelection={composerImageModelSelection}
            onPickFiles={(files) => void onPickFiles(files)}
            onFileSelection={onFileSelection}
            onRemoveAttachment={(index) =>
              setAttached((current) => current.filter((_, itemIndex) => itemIndex !== index))
            }
            onCancelEdit={() => setSelectedEditSource(null)}
            onReversePrompt={() => void send('反推这张图的提示词', [attached[0].id])}
            onClear={() => {
              setDraft('')
              setAttached([])
              setSelectedEditSource(null)
            }}
            onSend={() => void send(draft, attached.map((image) => image.id))}
          />
        </div>
      </main>
      <ChatImagePreviewDialog
        image={previewImage}
        onOpenChange={(open) => {
          if (!open) setPreviewImage(null)
        }}
        onEdit={selectEditSource}
      />
      <ReversePromptDialog
        source={reverseSource}
        onClose={() => setReverseSource(null)}
      />
    </AppShell>
  )
}

function Bubble({
  bubble, awaiting, onResolve, onOpenAction,
}: {
  bubble: ChatBubble
  awaiting: GenerationConfirm | null
  onResolve: (
    action: 'confirm' | 'cancel',
    confirmation: GenerationConfirm,
  ) => void
  onOpenAction: (action: ChatActionCard) => void
}) {
  if (bubble.role === 'user') {
    return (
      <div className="flex flex-col items-end gap-1.5">
        {bubble.images && bubble.images.length > 0 && (
          <div className="flex gap-1.5">
            {bubble.images.map((u, i) => (
              <img key={i} src={u} alt="" className="size-14 rounded-lg border border-wb-line-1 object-cover" />
            ))}
          </div>
        )}
        {bubble.text && (
          <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-wb-brand px-4 py-2.5 text-[14px] leading-relaxed text-white shadow-[0_8px_20px_-10px_rgba(91,91,214,.6)]">
            {bubble.text}
          </div>
        )}
      </div>
    )
  }

  const activeGeneration =
    bubble.generation &&
    awaiting?.confirmToken === bubble.generation.confirmToken
      ? bubble.generation
      : null
  return (
    <div className="flex justify-start">
      {/* glass-lite: bubbles live inside the scroller and grow unbounded — real
          backdrop-filter here would re-blur every bubble on each scrolled frame. */}
      <div className="glass-lite max-w-[88%] space-y-2.5 rounded-2xl rounded-tl-md px-4 py-3">
        {bubble.steps.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {bubble.steps.map((s, i) => (
              <span key={i} className="flex items-center gap-1 rounded-full bg-wb-tint-1 px-2 py-0.5 text-[11px] font-medium text-wb-brand-deep">
                <SparklesIcon className="size-3" />
                {PHASE_LABEL[s.phase] ?? s.phase}
                {s.detail ? ` · ${s.detail}` : ''}
              </span>
            ))}
          </div>
        )}
        {bubble.text && <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-wb-ink-2">{bubble.text}</p>}
        {bubble.generation && (
          <GenerationCard
            confirmation={bubble.generation}
            active={activeGeneration !== null}
            onResolve={onResolve}
          />
        )}
        {bubble.action && (
          <button
            type="button"
            onClick={() => onOpenAction(bubble.action!)}
            className="flex w-full items-center justify-between rounded-xl border border-wb-brand-soft bg-wb-tint-3 px-3.5 py-3 text-left text-[13px] font-semibold text-wb-brand-deep transition-colors hover:bg-wb-tint-1"
          >
            {bubble.action.label}
            <ArrowRightIcon className="size-4" />
          </button>
        )}
      </div>
    </div>
  )
}

function GenerationCard({
  confirmation,
  active,
  onResolve,
}: {
  confirmation: GenerationConfirm
  active: boolean
  onResolve: (
    action: 'confirm' | 'cancel',
    confirmation: GenerationConfirm,
  ) => void
}) {
  return (
    <div className="rounded-xl border border-wb-brand-soft bg-wb-tint-3 p-3">
      <p className="text-[13px] font-medium text-wb-ink-2">
        将使用
        <span className="mx-1 font-bold text-wb-brand-deep">
          {confirmation.modelDisplayName}
        </span>
        生成
        <span className="mx-1 font-bold text-wb-brand-deep">
          {confirmation.count}
        </span>
        张图片
      </p>
      <p className="mt-1 text-[11px] text-wb-ink-6">
        {confirmation.renderTier === '4k' ? '4K 超高清 · 3840×2160' : '标准档'}
        {confirmation.ratio ? ` · ${confirmation.ratio}` : ''}
      </p>
      {active ? (
        <div className="mt-2.5 flex gap-2">
          <button
            onClick={() => onResolve('confirm', confirmation)}
            className="rounded-full bg-gradient-to-r from-wb-grad-from to-wb-grad-to px-4 py-1.5 text-[12.5px] font-semibold text-white"
          >
            确认出图
          </button>
          <button
            onClick={() => onResolve('cancel', confirmation)}
            className="rounded-full border border-wb-line-1 bg-white px-4 py-1.5 text-[12.5px] font-medium text-wb-ink-4"
          >
            取消
          </button>
        </div>
      ) : (
        <p className="mt-2 text-[11.5px] font-medium text-wb-ink-5">已处理</p>
      )}
    </div>
  )
}
