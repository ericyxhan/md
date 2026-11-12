import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import StructureViewport from "./StructureViewport";

/**
 * The viewer asks for the headers before handing a URL to Mol*, so a
 * refused structure shows an error instead of an empty scene.  Endpoints
 * that do not answer HEAD must still work.
 */

const molstar = vi.hoisted(() => {
  const loadStructureFromUrl = vi.fn(async () => {});
  const dispose = vi.fn();
  const instance = { loadStructureFromUrl, dispose };
  return { loadStructureFromUrl, dispose, instance, create: vi.fn(async () => instance) };
});

vi.mock("molstar/lib/apps/viewer/app.js", () => ({
  Viewer: { create: molstar.create },
}));
vi.mock("molstar/build/viewer/molstar.css", () => ({}));

const originalFetch = globalThis.fetch;

describe("StructureViewport", () => {
  let headStatus: number;

  beforeEach(() => {
    headStatus = 200;
    globalThis.fetch = vi.fn(async (_url: unknown, init?: RequestInit) => {
      if (init?.method === "HEAD") {
        return {
          ok: headStatus >= 200 && headStatus < 300,
          status: headStatus,
          headers: new Headers({ "content-type": "chemical/x-pdb" }),
        } as Response;
      }
      return { ok: true, status: 200 } as Response;
    }) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it("loads the structure when the headers are available", async () => {
    render(<StructureViewport url="/api/v1/files/abc/preview" />);

    await waitFor(() =>
      expect(molstar.loadStructureFromUrl).toHaveBeenCalledWith(
        "/api/v1/files/abc/preview",
        "pdb",
        false,
        undefined,
      ),
    );
    expect(screen.queryByText(/could not be rendered/i)).toBeNull();
  });

  it("reports a refused structure instead of rendering an empty scene", async () => {
    headStatus = 409;
    render(<StructureViewport url="/api/v1/files/abc/preview" />);

    await waitFor(() =>
      expect(screen.getByText(/could not be rendered/i)).toBeTruthy(),
    );
    expect(screen.getByText(/HTTP 409/)).toBeTruthy();
    expect(molstar.loadStructureFromUrl).not.toHaveBeenCalled();
  });

  it("still loads when the endpoint does not answer HEAD", async () => {
    headStatus = 405;
    render(<StructureViewport url="/api/v1/jobs/1/artifacts/2" />);

    await waitFor(() =>
      expect(molstar.loadStructureFromUrl).toHaveBeenCalledWith(
        "/api/v1/jobs/1/artifacts/2",
        "pdb",
        false,
        undefined,
      ),
    );
    expect(screen.queryByText(/could not be rendered/i)).toBeNull();
  });
});
