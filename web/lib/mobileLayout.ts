import { useEffect, useState } from "react";
import type { RefObject } from "react";

export type PanelMode = "peek" | "split" | "expanded";

export const PEEK_HANDLE_PX = 30;
export const PEEK_BAR_PX = 44;
export const HEADER_GAP_PX = 8;
const SPLIT_MIN_CLEARANCE_PX = 120;
const SHEET_MIN_HEIGHT_PX = 200;

export type MobileLayout = {
  viewportHeight: number;
  headerBottom: number;
  safeBottom: number;
};

export type MapInsets = { top: number; right: number; bottom: number; left: number };

// Single source of truth for sheet geometry. The result is written to CSS custom
// properties on the app root, so CSS never duplicates these numbers.
export function sheetTop(mode: PanelMode, layout: MobileLayout): number {
  const { viewportHeight: vh, headerBottom, safeBottom } = layout;
  if (mode === "expanded") return headerBottom + HEADER_GAP_PX;
  if (mode === "peek") return vh - PEEK_HANDLE_PX - PEEK_BAR_PX - safeBottom;
  return Math.min(
    Math.max(headerBottom + SPLIT_MIN_CLEARANCE_PX, vh * 0.5),
    Math.max(headerBottom + SPLIT_MIN_CLEARANCE_PX, vh - SHEET_MIN_HEIGHT_PX),
  );
}

export function nearestPanelMode(top: number, layout: MobileLayout): PanelMode {
  const stops: PanelMode[] = ["expanded", "split", "peek"];
  return stops.reduce((best, mode) =>
    Math.abs(sheetTop(mode, layout) - top) < Math.abs(sheetTop(best, layout) - top) ? mode : best,
  );
}

// Area of the map that is not covered by the header or the sheet. Used to fit
// markers and center a selected pin. `null` means "no inset" (desktop or expanded).
export function visibleInsets(mode: PanelMode, layout: MobileLayout): MapInsets | null {
  if (mode === "expanded") return null;
  return {
    top: layout.headerBottom + HEADER_GAP_PX,
    right: 16,
    bottom: layout.viewportHeight - sheetTop(mode, layout) + 12,
    left: 16,
  };
}

function readSafeBottom(): number {
  const probe = document.createElement("div");
  probe.style.cssText = "position:fixed;left:0;bottom:0;width:0;height:0;visibility:hidden;padding-bottom:env(safe-area-inset-bottom,0px)";
  document.body.appendChild(probe);
  const value = parseFloat(getComputedStyle(probe).paddingBottom) || 0;
  probe.remove();
  return value;
}

// Returns null on desktop so that no mobile geometry leaks into desktop rendering.
export function useMobileLayout(
  appRef: RefObject<HTMLElement | null>,
  headRef: RefObject<HTMLElement | null>,
): MobileLayout | null {
  const [layout, setLayout] = useState<MobileLayout | null>(null);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 800px)");
    const measure = () => {
      const app = appRef.current;
      const head = headRef.current;
      if (!media.matches || !app || !head) {
        setLayout(null);
        return;
      }
      setLayout({
        viewportHeight: app.clientHeight,
        headerBottom: head.getBoundingClientRect().bottom,
        safeBottom: readSafeBottom(),
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (appRef.current) observer.observe(appRef.current);
    if (headRef.current) observer.observe(headRef.current);
    media.addEventListener("change", measure);
    return () => {
      observer.disconnect();
      media.removeEventListener("change", measure);
    };
  }, [appRef, headRef]);

  return layout;
}
