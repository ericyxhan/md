import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React, { Component, Suspense, type ReactNode } from "react";
import { lazyWithReload } from "./lazy";

/**
 * A redeploy replaces the content-hashed assets while a tab may still run
 * the previous build.  A dynamic import then 404s and the user is stuck on a
 * dead error boundary.  `lazyWithReload` reloads once to recover.
 */

const RELOAD_KEY = "md:chunk-reload-at";

/** Keeps a failed chunk import from becoming an unhandled error. */
class Boundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    return this.state.error ? <div>failed</div> : this.props.children;
  }
}

describe("lazyWithReload", () => {
  let reload: ReturnType<typeof vi.fn>;
  let originalLocation: Location;

  beforeEach(() => {
    reload = vi.fn();
    originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: { ...originalLocation, reload },
    });
    window.sessionStorage.clear();
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: originalLocation,
    });
  });

  it("renders the component when the chunk loads", async () => {
    const Loaded = lazyWithReload(async () => ({
      default: () => <div>chunk loaded</div>,
    }));

    render(
      <Suspense fallback={<div>loading…</div>}>
        <Loaded />
      </Suspense>,
    );

    await waitFor(() => expect(screen.getByText("chunk loaded")).toBeTruthy());
    expect(reload).not.toHaveBeenCalled();
  });

  it("reloads the page when the chunk cannot be fetched", async () => {
    const Broken = lazyWithReload(async () => {
      throw new TypeError(
        "Failed to fetch dynamically imported module: /assets/gone.js",
      );
    });

    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <Boundary>
        <Suspense fallback={<div>loading…</div>}>
          <Broken />
        </Suspense>
      </Boundary>,
    );

    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByText("failed")).toBeTruthy());
    spy.mockRestore();
  });

  it("does not reload twice within the cooldown", async () => {
    window.sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
    reload.mockClear();

    const Broken = lazyWithReload(async () => {
      throw new TypeError("Failed to fetch dynamically imported module");
    });

    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <Boundary>
        <Suspense fallback={<div>loading…</div>}>
          <Broken />
        </Suspense>
      </Boundary>,
    );

    await waitFor(() => expect(screen.getByText("failed")).toBeTruthy());
    expect(reload).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
