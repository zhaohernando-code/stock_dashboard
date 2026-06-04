export type RouteWriteMode = "push" | "replace";

export function readRouteParam(name: string): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get(name);
}

export function writeWorkbenchRoute(
  updates: Record<string, string | null | undefined>,
  mode: RouteWriteMode = "replace",
): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  Object.entries(updates).forEach(([key, value]) => {
    const normalized = (value ?? "").trim();
    if (normalized) {
      url.searchParams.set(key, normalized);
    } else {
      url.searchParams.delete(key);
    }
  });
  const next = `${url.pathname}${url.search}${url.hash}`;
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (next === current) return;
  window.history[mode === "push" ? "pushState" : "replaceState"](
    { ...(window.history.state ?? {}), ashareWorkbenchRoute: true },
    "",
    next,
  );
}
