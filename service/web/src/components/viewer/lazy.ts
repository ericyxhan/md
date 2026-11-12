import { lazyWithReload } from "../../lib/lazy";

/**
 * The single lazy boundary around Mol*-based components. Importing these
 * modules costs nothing; the heavy viewer chunk (~5 MB) is fetched only when
 * a component is actually rendered behind a Suspense boundary.
 */
export const LazyStructureViewport = lazyWithReload(
  () => import("./StructureViewport"),
);

export const LazyTrajectoryPlayer = lazyWithReload(
  () => import("./TrajectoryPlayer"),
);
