import { create } from 'zustand'

import type { ResultSlot } from '@/lib/listing'
import { DEFAULT_LISTING_CONFIG, type ListingConfig, type UploadedImage } from '@/lib/listing'

type Updater<T> = T | ((prev: T) => T)
function apply<T>(u: Updater<T>, prev: T): T {
  return typeof u === 'function' ? (u as (p: T) => T)(prev) : u
}

/**
 * 工作台「即时态」单一事实源（2026-07-01 恢复最近一单设计稿 §四）。
 *
 * 降级后本 store 只兜**服务端无记录的即时态**——跳页返回不丢即可：
 *  - 未提交态：config（配置）、uploaded（已上传但还没点生成的预览）。
 *  - 进行中态：activeJobId/activeSlots/activeGenerating —— 本会话刚发起、
 *    尚在生成的那一单。后端在终态前**不落库**，服务端「最近一单」查询读不到进行中行，
 *    故靠此即时态跨页续播（组件卸载状态仍在 store）。
 *
 * **终态结果不再存这里**：完成/失败的结果由服务端「最近一单」（GET /listing/jobs?limit=1
 * + 详情）驱动，故整页刷新 F5 也不丢。注：即时态仍是内存态，F5 会丢 —— 进行中单 F5
 * 后回落服务端最近一单（后端不落进行中行是已知边界，见设计稿 §五 / 交付说明）。
 */
interface WorkbenchState {
  config: ListingConfig
  uploaded: UploadedImage[]
  /** bump → 重挂 ConfigPanel 清空上传器内部态 */
  resetKey: number

  /** 本会话进行中的一单（发起→SSE 续播）；终态后由服务端最近一单接手。 */
  activeJobId: string | null
  activeSlots: ResultSlot[]
  /** true=SSE 仍在续播（未收到 completed/failed）。 */
  activeGenerating: boolean

  setConfig: (u: Updater<ListingConfig>) => void
  setUploaded: (u: Updater<UploadedImage[]>) => void
  setActiveJobId: (u: Updater<string | null>) => void
  setActiveSlots: (u: Updater<ResultSlot[]>) => void
  setActiveGenerating: (u: Updater<boolean>) => void
  /** 发起新一单：预铺槽位、进入续播态（job_id 稍后由请求返回回填）。 */
  startActive: (slots: ResultSlot[]) => void
  /** 接回服务端进行中单（F5 恢复）：已知 job_id + 计划张数，铺 shimmer 占位续播 SSE。 */
  adoptActive: (jobId: string, count: number) => void
  /** 请求失败/放弃 / 终态释放：清空进行中态（结果区回落服务端最近一单）。 */
  clearActive: () => void
  /** 「新建任务」：清即时态回到初始（含 bump resetKey 清上传器内部态）。 */
  reset: () => void
  /** 复用配方（ISSUE-0053）：以配方覆盖 config，清空 uploads（配方≠素材、产品图须自传）+
   *  重置进行中态（含 bump resetKey 重挂上传器/配置面板）。 */
  applyPrefill: (prefill: Partial<ListingConfig>) => void
}

const EMPTY_ACTIVE = {
  activeJobId: null,
  activeSlots: [] as ResultSlot[],
  activeGenerating: false,
}

export const useWorkbenchStore = create<WorkbenchState>((set) => ({
  config: DEFAULT_LISTING_CONFIG,
  uploaded: [],
  resetKey: 0,
  ...EMPTY_ACTIVE,

  setConfig: (u) => set((s) => ({ config: apply(u, s.config) })),
  setUploaded: (u) => set((s) => ({ uploaded: apply(u, s.uploaded) })),
  setActiveJobId: (u) => set((s) => ({ activeJobId: apply(u, s.activeJobId) })),
  setActiveSlots: (u) => set((s) => ({ activeSlots: apply(u, s.activeSlots) })),
  setActiveGenerating: (u) => set((s) => ({ activeGenerating: apply(u, s.activeGenerating) })),
  startActive: (slots) =>
    set({ activeJobId: null, activeSlots: slots, activeGenerating: true }),
  adoptActive: (jobId, count) =>
    set({
      activeJobId: jobId,
      // 无计划分型信息，铺无标签占位；SSE 到达的带型图按序填入（详见 WorkbenchPage 匹配）。
      activeSlots: Array.from({ length: count }, () => ({ url: null }) as ResultSlot),
      activeGenerating: true,
    }),
  clearActive: () => set({ ...EMPTY_ACTIVE }),
  reset: () =>
    set((s) => ({
      config: DEFAULT_LISTING_CONFIG,
      uploaded: [],
      resetKey: s.resetKey + 1,
      ...EMPTY_ACTIVE,
    })),
  applyPrefill: (prefill) =>
    set((s) => ({
      config: { ...DEFAULT_LISTING_CONFIG, ...prefill },
      uploaded: [],
      resetKey: s.resetKey + 1,
      ...EMPTY_ACTIVE,
    })),
}))
