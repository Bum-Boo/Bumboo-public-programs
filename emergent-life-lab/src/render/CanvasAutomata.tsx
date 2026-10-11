
import { forwardRef, useEffect, useEffectEvent, useImperativeHandle, useRef, type MutableRefObject } from "react";
import type { GridBuffer, RuleDefinition } from "@/src/ca/types";
import { CELL_PALETTE, colorForState, colorForWireWorldState } from "@/src/render/palette";
import styles from "@/src/app/App.module.css";

export type CanvasAutomataHandle = {
  exportPng: () => string | null;
  drawNow: () => void;
};

type CanvasAutomataProps = {
  gridRef: MutableRefObject<GridBuffer>;
  rule: RuleDefinition;
  brushSize: number;
  erasing: boolean;
  onPaint: (x: number, y: number, erase: boolean) => void;
};

function getAutomataRenderDpr() {
  const nativeDpr = window.devicePixelRatio || 1;
  const shortSide = Math.min(window.innerWidth, window.innerHeight);
  const cap = shortSide <= 480 ? 1.25 : shortSide <= 900 ? 1.5 : 2;
  return Math.min(nativeDpr, cap);
}

export const CanvasAutomata = forwardRef<CanvasAutomataHandle, CanvasAutomataProps>(function CanvasAutomata(
  { gridRef, rule, brushSize, erasing, onPaint },
  ref
) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sizeRef = useRef({ width: 0, height: 0, dpr: 1 });
  const pointerDownRef = useRef(false);
  const ruleRef = useRef(rule);

  useEffect(() => {
    ruleRef.current = rule;
  }, [rule]);

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }

    const grid = gridRef.current;
    const { width, height } = sizeRef.current;
    if (width <= 0 || height <= 0) {
      return;
    }

    const cellSize = Math.min(width / grid.width, height / grid.height);
    const offsetX = (width - grid.width * cellSize) / 2;
    const offsetY = (height - grid.height * cellSize) / 2;

    context.clearRect(0, 0, width, height);
    context.fillStyle = CELL_PALETTE.background;
    context.fillRect(0, 0, width, height);

    context.save();
    context.translate(offsetX, offsetY);

    const useWireColors = ruleRef.current.kind === "wireworld";
    for (let y = 0; y < grid.height; y += 1) {
      for (let x = 0; x < grid.width; x += 1) {
        const state = grid.cells[y * grid.width + x];
        if (state === 0) {
          continue;
        }

        context.fillStyle = useWireColors ? colorForWireWorldState(state) : colorForState(state);
        const inset = cellSize > 8 ? 0.9 : 0.25;
        context.fillRect(x * cellSize + inset, y * cellSize + inset, Math.max(1, cellSize - inset * 2), Math.max(1, cellSize - inset * 2));
      }
    }

    if (cellSize >= 7) {
      context.strokeStyle = CELL_PALETTE.grid;
      context.lineWidth = 1;
      context.beginPath();
      for (let x = 0; x <= grid.width; x += 1) {
        const px = Math.round(x * cellSize) + 0.5;
        context.moveTo(px, 0);
        context.lineTo(px, grid.height * cellSize);
      }
      for (let y = 0; y <= grid.height; y += 1) {
        const py = Math.round(y * cellSize) + 0.5;
        context.moveTo(0, py);
        context.lineTo(grid.width * cellSize, py);
      }
      context.stroke();
    }

    context.restore();
  };

  useImperativeHandle(ref, () => ({
    exportPng: () => canvasRef.current?.toDataURL("image/png") ?? null,
    drawNow: draw
  }));

  // The resize observer and render loop are set up once; this always draws with the latest props.
  const drawFrame = useEffectEvent(() => {
    draw();
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const updateSize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = getAutomataRenderDpr();
      sizeRef.current = { width: rect.width, height: rect.height, dpr };
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      const context = canvas.getContext("2d");
      context?.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawFrame();
    };

    const observer = new ResizeObserver(updateSize);
    observer.observe(canvas);
    updateSize();

    let frame = 0;
    const render = () => {
      drawFrame();
      frame = window.requestAnimationFrame(render);
    };
    frame = window.requestAnimationFrame(render);

    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frame);
    };
  }, []);

  const paintFromEvent = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const grid = gridRef.current;
    const rect = canvas.getBoundingClientRect();
    const cellSize = Math.min(rect.width / grid.width, rect.height / grid.height);
    const offsetX = (rect.width - grid.width * cellSize) / 2;
    const offsetY = (rect.height - grid.height * cellSize) / 2;
    const x = Math.floor((event.clientX - rect.left - offsetX) / cellSize);
    const y = Math.floor((event.clientY - rect.top - offsetY) / cellSize);

    if (x >= 0 && x < grid.width && y >= 0 && y < grid.height) {
      onPaint(x, y, erasing || event.altKey);
      draw();
    }
  };

  return (
    <div className={styles.canvasShell}>
      <canvas
        ref={canvasRef}
        className={styles.canvas}
        aria-label="Interactive cellular automata canvas"
        onPointerDown={(event) => {
          pointerDownRef.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
          paintFromEvent(event);
        }}
        onPointerMove={(event) => {
          if (pointerDownRef.current) {
            paintFromEvent(event);
          }
        }}
        onPointerUp={(event) => {
          pointerDownRef.current = false;
          event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={() => {
          pointerDownRef.current = false;
        }}
      />
      <div className={styles.canvasLegend} aria-hidden="true">
        <span>{erasing ? "Erase mode" : "Paint mode"}</span>
        <strong>{brushSize} cell brush</strong>
      </div>
    </div>
  );
});
