"use client";

import { useEffect, useRef } from "react";

import { ecgChunks } from "@/lib/live/ecg-buffer";
import { useLive } from "@/lib/live/store";
import { cn } from "@/lib/utils";

const DELAY_MS = 1400; // play slightly behind real time so one-second chunks arrive first
const Y_MIN = -0.7;
const Y_MAX = 1.6;

/**
 * Bedside-monitor style ECG sweep. The write head moves left to right and erases just ahead of
 * itself; samples sit at fixed x positions derived from their timestamps, so the trace is stable
 * regardless of frame rate. Draws to canvas from a mutable buffer: no React re-render per frame.
 */
export function EcgTrace({
  astronautId,
  sweepSeconds = 6,
  className,
  grid = false,
  label,
}: {
  astronautId: string;
  sweepSeconds?: number;
  className?: string;
  grid?: boolean;
  label?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const styles = getComputedStyle(canvas);
    const trace = styles.getPropertyValue("--telemetry").trim() || "#3dd8ea";
    const gridColor = "rgba(61, 216, 234, 0.07)";
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let width = 0;
    let height = 0;
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);

    const windowMs = sweepSeconds * 1000;
    const gapMs = windowMs * 0.05;
    const y = (mv: number) => height - ((mv - Y_MIN) / (Y_MAX - Y_MIN)) * height;

    let frame = 0;
    let timer: ReturnType<typeof setInterval> | null = null;

    const draw = () => {
      ctx.clearRect(0, 0, width, height);
      if (grid) {
        ctx.strokeStyle = gridColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        const step = width / (sweepSeconds * 5); // 200 ms major grid
        for (let x = step; x < width; x += step) {
          ctx.moveTo(Math.round(x) + 0.5, 0);
          ctx.lineTo(Math.round(x) + 0.5, height);
        }
        for (let v = -0.5; v <= 1.5; v += 0.5) {
          ctx.moveTo(0, Math.round(y(v)) + 0.5);
          ctx.lineTo(width, Math.round(y(v)) + 0.5);
        }
        ctx.stroke();
      }

      const offset = useLive.getState().serverOffsetMs ?? 0;
      const head = Date.now() + offset - DELAY_MS;
      const start = head - windowMs + gapMs;
      const chunks = ecgChunks(astronautId);

      ctx.strokeStyle = trace;
      ctx.lineWidth = 1.6;
      ctx.lineJoin = "round";
      ctx.beginPath();
      let prevX = -1;
      let prevT = -Infinity;
      let headPoint: [number, number] | null = null;
      for (const chunk of chunks) {
        const dt = 1000 / chunk.fs;
        const chunkEnd = chunk.start + chunk.values.length * dt;
        if (chunkEnd < start || chunk.start > head) continue;
        for (let i = 0; i < chunk.values.length; i++) {
          const t = chunk.start + i * dt;
          if (t < start || t > head) continue;
          const x = ((t % windowMs) / windowMs) * width;
          const yy = y(chunk.values[i]);
          if (x < prevX || t - prevT > dt * 2.5) ctx.moveTo(x, yy);
          else ctx.lineTo(x, yy);
          prevX = x;
          prevT = t;
          headPoint = [x, yy];
        }
      }
      ctx.stroke();

      if (headPoint && head - prevT < 500) {
        ctx.fillStyle = trace;
        ctx.shadowColor = trace;
        ctx.shadowBlur = 8;
        ctx.beginPath();
        ctx.arc(headPoint[0], headPoint[1], 2.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
      }
      canvas.dataset.signal = headPoint ? "yes" : "no";
    };

    const loop = () => {
      draw();
      frame = requestAnimationFrame(loop);
    };
    if (reduceMotion) {
      draw();
      timer = setInterval(draw, 1000);
    } else {
      frame = requestAnimationFrame(loop);
    }

    return () => {
      cancelAnimationFrame(frame);
      if (timer) clearInterval(timer);
      observer.disconnect();
    };
  }, [astronautId, sweepSeconds, grid]);

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label={label ?? `Live synthetic ECG for ${astronautId}`}
      className={cn("block h-full w-full", className)}
    />
  );
}
