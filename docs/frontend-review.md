# Frontend (service/web) — review & optimization opportunities

Baseline: 14 test files, 48 tests passing; `npm run typecheck` + `npm run build` clean.
Bundle: main chunk ~93 KB gzipped; molstar isolated to a ~5 MB lazy chunk fetched
only when a viewer renders. Code-splitting by route is already in place.

## 1. High value

### 1.1 Extract a shared prep-job view
`MembraneEmbedPage` and `DockingPage` (and `SystemPrepPage`) each reimplement
the same job view: status badge, phase, progress bar + message, error panel,
output-file list with download + "use in simulation", cancel button, refresh.
That is ~250 lines duplicated per page and the reason the new Docking page
took a large copy. **Recommendation:** introduce
`components/prep/PrepJobView.tsx` taking `prepJob`, `labels` (title, output
names, use-in-simulation handler) and `onCancel`. Membrane and Docking become
thin wrappers. Effort: medium. Risk: low (pure extraction, tests cover
Membrane).

### 1.2 Split `JobDetailPage.tsx` (948 lines)
It owns overview, stages, events, logs, artifacts, and config tabs in one
file. Tab bodies should be co-located components (`JobOverviewTab`,
`JobStagesTab`, …) loaded lazily. Effort: medium. Benefit: smaller chunks,
easier review.

### 1.3 Split `api.ts` (616 lines) by domain
One file for jobs, prep, files, admin, workflows. Improves tree-shaking
discoverability and reviewability. Effort: low. Risk: low (pure move).

## 2. Medium value

### 2.1 Type filter for `usePrepJobs`
Every prep page fetches all prep jobs and filters client-side by `type`. Add
an optional `type` param to `listPrepJobs`/`usePrepJobs` to reduce payload and
re-rend. Effort: low (backend already supports filtering? check; if not, add).

### 2.2 Memoize list rows
`PrepJobRow` and the job cards are not memoized; large lists re-render on
every poll. Wrap in `React.memo` and pass stable props. Effort: low.

### 2.3 Stable query keys
`queryKeys.job(id)` returns a new array each call but React Query compares by
value, so it's fine. However `useJobs` spreads `[...queryKeys.jobs(status), limit]`,
creating a new array identity each render — harmless but noisy. Consolidate.

### 2.4 Remove dead code
Unused imports/locals flagged by `noUnusedLocals` (see §4). A first pass
cleaned DockingPage, queries.ts, api.ts. Remaining: ~30 sites in pages
(`WorkflowDetailPage`, `AdminJobsPage`, `DashboardPage`, `NewJobPage`,
`StepStructure`, `StepReview`, `AnalysisPanel`, viewer components). Effort: low.

### 2.5 `useLogTail` dependency on job query
It reads the job from the query cache via `queryClient.getQueryData`. Works,
but a cleaner contract would pass `jobStatus` as a param. Effort: low.

## 3. Bundle / performance

### 3.1 Already good
- Route-level lazy loading via `lazyWithReload`.
- Mol* isolated behind `LazyStructureViewport`/`LazyTrajectoryPlayer`.
- Chunk-reload recovery on redeploy.

### 3.2 Opportunities
- `recharts` (~? KB) is imported by analysis pages; ensure those routes stay
  lazy (they are). Verify no eager import in `App.tsx`.
- `molstar` CSS is imported inside the lazy component (good).
- Consider `React.memo` on `ProgressBar`, `Badge` (cheap).

## 4. Unused symbols (from `noUnusedLocals` pass)

AnalysisPanel: `useMemo`, `Button`.
EditStack: `Plus`.
SelectionPanel: `Button`.
AdminJobsPage: `active`.
DashboardPage: `PageLoader`, `cn`.
JobDetailPage: `lazy`, `Droplets`.
NewJobPage: `FileOut`, `navigate` (unused in one scope).
WorkflowDetailPage: `useCallback`, `FileBox`, `Loader2`, `Trash2`,
  `getWorkflow`, `useCapabilities`, `useWorkflows`, `ProgressBar`, `cn`,
  `formatCompact`, `isActive`, `isTerminal`, `WorkflowDetailOut`,
  `activeJobs`, `completedJobs`, `failedJobs`.
WorkflowsPage: `cn`, `activeJobs`, `w`.
StepReview: `humanizeStage`, `titleCase`.
StepStructure: `Suspense`, `label`, `hasStructure`.
DockingPage: cleaned.

## 5. Accessibility / UX

- Destructive actions use `window.confirm` in some places; consider the
  existing `Modal` primitive for consistency.
- Several pages lack loading skeletons (use `PageLoader` consistently).
- Form inputs in DockingPage use raw `<input>` instead of the shared `Field`
  + control; align with the design system.

## 6. Recommended order

1. §1.1 extract prep view (biggest duplication win, unblocks future prep pages).
2. §2.4 dead-code cleanup (mechanical, safe).
3. §1.2 split JobDetailPage.
4. §2.1 type-filtered prep jobs.
5. §1.3 split api.ts.
