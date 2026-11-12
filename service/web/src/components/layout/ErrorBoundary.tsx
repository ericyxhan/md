import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "../ui/Button";

type Props = {
  children: ReactNode;
};

type State = {
  error: Error | null;
};

/**
 * Catches render-time errors anywhere below it and shows a recoverable
 * message instead of an empty page.
 *
 * React unmounts the whole tree when a render throws and there is no
 * boundary above it, which looks like a blank screen until a refresh.  This
 * boundary turns that into a visible, actionable error.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep the detail in the console for support; the UI stays calm.
    console.error("Unhandled UI error:", error, info.componentStack);
  }

  private reset = () => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="mx-auto flex min-h-[60vh] w-full max-w-[620px] flex-col items-center justify-center px-6 text-center">
        <span className="flex size-11 items-center justify-center rounded-full bg-rose-50 text-rose-600">
          <AlertTriangle className="size-5" />
        </span>
        <h2 className="mt-4 text-[16px] font-semibold text-ink">
          This view could not be displayed
        </h2>
        <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-muted">
          Something went wrong while rendering this page. Reloading usually
          clears it; if it keeps happening, check the browser console for
          details.
        </p>
        <pre className="mt-4 max-w-full overflow-x-auto rounded-lg bg-surface-muted px-3 py-2 text-[11px] text-muted">
          {error.message}
        </pre>
        <div className="mt-5 flex items-center gap-2">
          <Button
            variant="primary"
            leadingIcon={<RotateCcw className="size-4" />}
            onClick={this.reset}
          >
            Try again
          </Button>
          <Button variant="secondary" onClick={() => window.location.reload()}>
            Reload page
          </Button>
        </div>
      </div>
    );
  }
}
