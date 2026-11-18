// The status questions every screen asks, typed against the wire unions (marcus/core/enums.py).
import type { ImageJobStatus, PaperStatus, StepStatus } from "./types";

const ACTIVE_STEP: ReadonlySet<string> = new Set<StepStatus>(["pending", "queued", "running"]);
const BUSY_PAPER: ReadonlySet<string> = new Set<PaperStatus>(["checking", "processing"]);
const ACTIVE_IMAGE: ReadonlySet<string> = new Set<ImageJobStatus>(["queued", "processing"]);

/** A step still to run or running. */
export const isStepActive = (status: string): boolean => ACTIVE_STEP.has(status);

/** A paper still being worked on (checked or processed). */
export const isPaperBusy = (status: string): boolean => BUSY_PAPER.has(status);

/** An image job still being worked on. */
export const isImageActive = (status: string): boolean => ACTIVE_IMAGE.has(status);
