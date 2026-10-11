export const CELL_PALETTE = {
  background: "#F8FBFF",
  grid: "#D9E4F2",
  alive: "#163A7A",
  liveAccent: "#2B63D9",
  dying: "#7E99BD",
  electronHead: "#2B63D9",
  electronTail: "#F2C84B",
  conductor: "#9FB4D3"
} as const;

export function colorForState(state: number) {
  if (state === 1) {
    return CELL_PALETTE.alive;
  }

  if (state === 2) {
    return CELL_PALETTE.dying;
  }

  if (state === 3) {
    return CELL_PALETTE.conductor;
  }

  return CELL_PALETTE.background;
}

export function colorForWireWorldState(state: number) {
  if (state === 1) {
    return CELL_PALETTE.electronHead;
  }

  if (state === 2) {
    return CELL_PALETTE.electronTail;
  }

  if (state === 3) {
    return CELL_PALETTE.conductor;
  }

  return CELL_PALETTE.background;
}
