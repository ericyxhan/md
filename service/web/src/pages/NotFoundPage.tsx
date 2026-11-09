import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-lg py-16">
      <div className="card">
        <EmptyState
          icon={<Compass className="size-5" />}
          title="Page not found"
          description="That route does not exist. The workspace may have moved, or the link is out of date."
          action={
            <Link to="/">
              <Button variant="primary">Back to overview</Button>
            </Link>
          }
        />
      </div>
    </div>
  );
}
