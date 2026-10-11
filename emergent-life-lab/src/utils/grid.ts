import type { GridBuffer } from "@/src/ca/types";

export function createGrid(width: number, height: number): GridBuffer {
  return {
    width,
    height,
    cells: new Uint8Array(width * height)
  };
}

export function clearGrid(grid: GridBuffer) {
  grid.cells.fill(0);
}

function indexOf(width: number, x: number, y: number) {
  return y * width + x;
}

export function setCell(grid: GridBuffer, x: number, y: number, state: number) {
  if (x < 0 || x >= grid.width || y < 0 || y >= grid.height) {
    return;
  }

  grid.cells[indexOf(grid.width, x, y)] = state;
}

export function paintDisc(grid: GridBuffer, centerX: number, centerY: number, radius: number, state: number) {
  const size = Math.max(1, Math.floor(radius));
  const radiusSquared = size * size;

  for (let y = centerY - size; y <= centerY + size; y += 1) {
    for (let x = centerX - size; x <= centerX + size; x += 1) {
      const dx = x - centerX;
      const dy = y - centerY;

      if (dx * dx + dy * dy <= radiusSquared) {
        setCell(grid, x, y, state);
      }
    }
  }
}

export function randomizeGrid(grid: GridBuffer, density: number, maxState = 1) {
  const clampedDensity = Math.min(1, Math.max(0, density));
  for (let index = 0; index < grid.cells.length; index += 1) {
    grid.cells[index] = Math.random() < clampedDensity ? Math.max(1, Math.floor(Math.random() * maxState) + 1) : 0;
  }
}
