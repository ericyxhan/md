import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ActivityPage } from "./ActivityPage";

const api = vi.hoisted(() => ({
  getEvents: vi.fn(),
  listJobs: vi.fn(),
  listPrepJobs: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  getEvents: api.getEvents,
  listJobs: api.listJobs,
  listPrepJobs: api.listPrepJobs,
}));

const item = (id: number, message: string, type = "completed") => ({
  id,
  created_at: new Date().toISOString(),
  type,
  message,
  data: null,
  job_id: "job-1",
  job_name: "Simulation one",
  job_status: "completed",
  source: "job" as const,
  prep_type: null,
});

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ActivityPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ActivityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listJobs.mockResolvedValue({ items: [], next_cursor: null });
    api.listPrepJobs.mockResolvedValue([]);
    api.getEvents.mockResolvedValue({
      items: [item(1, "Job finished")],
      next_cursor: null,
    });
  });

  it("renders the activity feed", async () => {
    renderPage();

    expect(await screen.findByText("Job finished")).toBeInTheDocument();
    expect(screen.getByText("All activity")).toBeInTheDocument();
    expect(screen.getByText("You're all caught up")).toBeInTheDocument();
  });

  it("filters the feed by event type", async () => {
    api.getEvents.mockResolvedValue({ items: [], next_cursor: null });
    renderPage();

    const select = screen.getByLabelText("Filter by event type");
    await waitFor(() => expect(api.getEvents).toHaveBeenCalled());

    // Selecting the option re-queries the feed with the filter.
    await userEvent.selectOptions(select, "failed");

    await waitFor(() =>
      expect(api.getEvents).toHaveBeenCalledWith(
        expect.objectContaining({ eventType: "failed" }),
      ),
    );
    expect(
      await screen.findByText("Nothing matches these filters"),
    ).toBeInTheDocument();
  });

  it("pages backwards with the opaque cursor", async () => {
    api.getEvents
      .mockResolvedValueOnce({
        items: [item(1, "Newer event")],
        next_cursor: "cursor-1",
      })
      .mockResolvedValueOnce({
        items: [item(2, "Older event")],
        next_cursor: null,
      });

    renderPage();

    expect(await screen.findByText("Newer event")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));

    expect(await screen.findByText("Older event")).toBeInTheDocument();
    expect(api.getEvents).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: "cursor-1" }),
    );
    expect(screen.getByText("You're all caught up")).toBeInTheDocument();
  });

  it("shows the error state when the feed fails to load", async () => {
    api.getEvents.mockRejectedValue(new Error("backend is down"));
    renderPage();

    expect(await screen.findByText("backend is down")).toBeInTheDocument();
  });
});
