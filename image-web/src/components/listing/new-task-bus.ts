// Tiny pub/sub so the layout's "新建任务" button can reset WorkbenchPage state.
type Listener = () => void
const listeners = new Set<Listener>()
export const newTaskBus = {
  emit: () => listeners.forEach((l) => l()),
  subscribe: (l: Listener) => {
    listeners.add(l)
    return () => {
      listeners.delete(l)
    }
  },
}
