import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { useBackgroundReplace } from '@/api/image-tools'
import { isModelUnavailableError, useListingEvents } from '@/api/listing'
import { BackgroundConfigPanel } from '@/components/listing/BackgroundConfigPanel'
import { ResultGallery } from '@/components/listing/ResultGallery'
import { newTaskBus } from '@/components/listing/new-task-bus'
import { useTerminalJobReconciliation } from '@/components/listing/use-terminal-job-reconciliation'
import {
  requireSelectedImageModel,
  useImageModelSelection,
} from '@/components/models/image-model-context'
import { ImageModelSelector } from '@/components/models/ImageModelSelector'
import {
  backgroundWorkbenchStateFromPrefill,
  closestSupportedRatio,
  type BackgroundWorkbenchPrefill,
  type BackgroundWorkbenchState,
} from '@/lib/image-tools'
import { uploadIdPreviewUrl, uploadPreviewUrl } from '@/lib/upload'
import {
  applyListingEventToSlots,
  mergeSlotsWithDetail,
  settledSlotCount,
  type ResultSlot,
  type UploadedImage,
} from '@/lib/listing'
import { useAuthStore } from '@/stores/auth-store'

interface BackgroundRouteState {
  prefill?: BackgroundWorkbenchPrefill
}

export function BackgroundWorkbenchPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const token = useAuthStore((state) => state.token)
  const routePrefill = (location.state as BackgroundRouteState | null)?.prefill
  const [state, setState] = useState<BackgroundWorkbenchState>(() =>
    backgroundWorkbenchStateFromPrefill(routePrefill, (id) =>
      uploadIdPreviewUrl(id, token),
    ),
  )
  const [ratio, setRatio] = useState<string | null>(null)
  const [resetKey, setResetKey] = useState(0)
  const [jobId, setJobId] = useState<string | null>(null)
  const [slots, setSlots] = useState<ResultSlot[]>([])
  const [completedJobId, setCompletedJobId] = useState<string>()
  const replaceBackground = useBackgroundReplace()
  const modelSelection = useImageModelSelection()
  const reconciliation = useTerminalJobReconciliation((detail) => {
    setSlots((current) => mergeSlotsWithDetail(current, detail.images))
    setCompletedJobId(detail.job_id)
  })

  useEffect(() => {
    if (location.state) {
      navigate(location.pathname, { replace: true, state: null })
    }
  }, [location.pathname, location.state, navigate])

  useEffect(
    () =>
      newTaskBus.subscribe(() => {
        setState(
          backgroundWorkbenchStateFromPrefill(undefined, () => ''),
        )
        setRatio(null)
        setResetKey((key) => key + 1)
        setJobId(null)
        setSlots([])
        setCompletedJobId(undefined)
        reconciliation.reset()
      }),
    [reconciliation],
  )

  useListingEvents(jobId, {
    onEvent: (event) => {
      if (event.kind === 'image' || event.kind === 'image_failed') {
        setSlots((current) => applyListingEventToSlots(current, event))
      } else if (event.kind === 'completed' || event.kind === 'failed') {
        if (event.kind === 'failed') toast.error(`换背景失败：${event.error}`)
        if (jobId) {
          void reconciliation.reconcile(jobId).catch(() =>
            toast.error('结果校准失败，请在历史记录中查看'),
          )
        }
        setJobId(null)
      }
    },
    onContractError: () => {
      setJobId(null)
      toast.error('图片事件格式异常')
    },
  })

  function setSourceUpload(image: UploadedImage | null) {
    setRatio(null)
    setState((current) => ({
      ...current,
      source: image
        ? {
            kind: 'upload',
            uploadId: image.id,
            previewUrl: uploadPreviewUrl(image.url, token),
          }
        : null,
    }))
  }

  function setReferenceUpload(image: UploadedImage | null) {
    setState((current) => ({
      ...current,
      reference: image
        ? {
            uploadId: image.id,
            previewUrl: uploadPreviewUrl(image.url, token),
          }
        : null,
    }))
  }

  async function generate() {
    if (!state.source) return
    const imageModel = requireSelectedImageModel(modelSelection)
    const background =
      state.backgroundMode === 'description'
        ? {
            kind: 'description' as const,
            description: state.description,
          }
        : state.reference
          ? {
              kind: 'reference' as const,
              uploadId: state.reference.uploadId,
              instruction: state.instruction,
            }
          : null
    if (!background) return

    reconciliation.reset()
    setCompletedJobId(undefined)
    setSlots([{ url: null }])
    try {
      const { job_id } = await replaceBackground.mutateAsync({
        imageModel,
        source: state.source,
        background,
      })
      setJobId(job_id)
    } catch (error) {
      setSlots([])
      if (isModelUnavailableError(error)) {
        modelSelection.retry()
        toast.error('刚选择的图片模型已不可用，换背景设置已保留，请重新选择。')
      } else {
        toast.error(
          error instanceof Error ? error.message : '换背景请求失败',
        )
      }
    }
  }

  const generating = replaceBackground.isPending || jobId !== null

  return (
    <>
      <BackgroundConfigPanel
        key={resetKey}
        state={state}
        ratio={ratio}
        pending={generating}
        modelReady={modelSelection.state === 'ready'}
        modelSelector={
          <ImageModelSelector
            selection={modelSelection}
            disabled={generating}
          />
        }
        onChange={setState}
        onSourceUpload={setSourceUpload}
        onReferenceUpload={setReferenceUpload}
        onSourceDimensions={(width, height) =>
          setRatio(closestSupportedRatio(width, height))
        }
        onGenerate={() => void generate()}
      />
      <ResultGallery
        title="换背景"
        slots={slots}
        done={settledSlotCount(slots)}
        total={slots.length}
        generating={generating}
        emptyHint="选择商品图和目标背景，点「开始换背景」"
        resultLabel="换背景成品"
        editJobId={completedJobId}
      />
    </>
  )
}
