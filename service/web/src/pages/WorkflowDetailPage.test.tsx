import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { WorkflowDetailPage } from "./WorkflowDetailPage";
import { ToastProvider } from "../components/ui/Toast";
import { getWorkflow } from "../lib/api";

/**
 * The page used to declare hooks after its loading and not-found early
 * returns, so React threw "Rendered more hooks than during the previous
 * render" as soon as the workflow finished loading.  These tests render the
 * page through that transition.
 */

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>(
    "../lib/api",
  );
  return { ...actual, getWorkflow: vi.fn() };
});

const WORKFLOW = {
  id: "wf-0001",
  name: "Membrane system",
  source_file_id: "file-0001",
  source_type: "membrane_embed",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  jobs: [
    {
      id: "job-0001",
      name: "Replicate 1",
      status: "running",
      phase: null,
      progress: {
        step: 10,
        total_steps: 100,
        percent: 10,
        updated_at: null,
      },
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
};

function renderPage() {
  const router = createMemoryRouter(
    [{ path: "/workflows/:workflowId", element: <WorkflowDetailPage /> }],
    { initialEntries: ["/workflows/wf-0001"] },
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("WorkflowDetailPage", () => {
  beforeEach(() => {
    vi.mocked(getWorkflow).mockReset();
  });

  it("renders the loading state and then the workflow without a hooks error", async () => {
    let resolveWorkflow: (value: unknown) => void = () => {};
    vi.mocked(getWorkflow).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveWorkflow = resolve;
        }) as never,
    );

    renderPage();
    expect(screen.getByText(/Loading workflow/i)).toBeTruthy();

    resolveWorkflow(WORKFLOW);

    await waitFor(() =>
      expect(screen.getByText("Membrane system")).toBeTruthy(),
    );
  });

  it("renders the not-found state when the workflow is missing", async () => {
    vi.mocked(getWorkflow).mockResolvedValue(undefined as never);

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/Workflow not found/i)).toBeTruthy(),
    );
  });
});
