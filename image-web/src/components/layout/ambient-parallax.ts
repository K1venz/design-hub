export function calculateLayerOffset(
  depth: number,
  pointerX: number,
  pointerY: number,
  scrollY: number,
) {
  return {
    x: pointerX * 16 * depth,
    y: pointerY * 16 * depth - scrollY * 0.02 * depth,
  }
}
