import { lazy, type ComponentType, type LazyExoticComponent } from "react";

/**
 * `React.lazy` with a one-shot recovery when a chunk cannot be fetched.
 *
 * The built assets are content-hashed and served with a long-lived immutable
 * cache, but a redeploy replaces them wholesale.  A tab that was already
 * running the previous build then asks for chunks that no longer exist and
 * the dynamic import fails with "Failed to fetch dynamically imported
 * module".  Reloading fetches the current index.html, which points at the
 * matching chunks.
 *
 * The reload is rate limited so a chunk that genuinely cannot be loaded
 * cannot turn into a reload loop: after one reload the error is surfaced
 * normally.
 */

const RELOAD_KEY = "md:chunk-reload-at";

/** Minimum gap between two automatic reloads, in milliseconds. */
const RELOAD_COOLDOWN_MS = 60_000;

function reloadOnce(): void {
  let last = 0;
  try {
    last = Number(window.sessionStorage.getItem(RELOAD_KEY) ?? "0");
  } catch {
    // Private mode or a blocked storage partition; fall back to reloading.
  }
  if (Date.now() - last < RELOAD_COOLDOWN_MS) return;
  try {
    window.sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  } catch {
    // Ignore: the cooldown is best effort.
  }
  window.location.reload();
}

export function lazyWithReload<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
): LazyExoticComponent<T> {
  return lazy(async () => {
    try {
      return await factory();
    } catch (error) {
      reloadOnce();
      throw error;
    }
  });
}

/**
 * Vite reports a failed dynamic import of a preloaded dependency through
 * this event.  Reloading is the same recovery as above.
 */
export function installChunkReloadHandler(): void {
  window.addEventListener("vite:preloadError", (event) => {
    event.preventDefault();
    reloadOnce();
  });
}
