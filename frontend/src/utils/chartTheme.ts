import { useEffect, useState } from "react";

export interface DashboardChartTheme {
  textColor: string;
  mutedColor: string;
  lineColor: string;
  tooltipBackgroundColor: string;
  tooltipTextColor: string;
  brandColor: string;
  goldColor: string;
  greenColor: string;
}

function cssValue(styles: CSSStyleDeclaration, name: string, fallback: string): string {
  return styles.getPropertyValue(name).trim() || fallback;
}

export function readDashboardChartTheme(container: HTMLElement): DashboardChartTheme {
  const styles = getComputedStyle(container);
  return {
    textColor: cssValue(styles, "--text-main", "#10233c"),
    mutedColor: cssValue(styles, "--text-muted", "#64748b"),
    lineColor: cssValue(styles, "--chart-grid", cssValue(styles, "--line", "rgba(16, 35, 60, 0.08)")),
    tooltipBackgroundColor: cssValue(styles, "--chart-tooltip-bg", "rgba(15, 35, 64, 0.92)"),
    tooltipTextColor: cssValue(styles, "--chart-tooltip-text", "#f8fbff"),
    brandColor: cssValue(styles, "--chart-series-primary", cssValue(styles, "--brand", "#0a5bff")),
    goldColor: cssValue(styles, "--chart-series-gold", "#d48700"),
    greenColor: cssValue(styles, "--chart-series-green", "#0b8f63"),
  };
}

export function useDashboardThemeRevision(): number {
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const bump = () => setRevision((current) => current + 1);
    const observer = new MutationObserver(bump);
    const options: MutationObserverInit = { attributes: true, attributeFilter: ["data-theme", "style", "class"] };
    observer.observe(document.documentElement, options);
    observer.observe(document.body, options);
    document.querySelectorAll(".app-theme-shell").forEach((node) => observer.observe(node, options));
    return () => observer.disconnect();
  }, []);

  return revision;
}
