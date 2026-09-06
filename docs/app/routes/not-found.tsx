import { HomeLayout } from 'fumadocs-ui/layouts/home';
import { Link } from 'react-router';
import { baseOptions } from '@/lib/layout.shared';

export function meta() {
  return [{ title: 'Page Not Found — Parlot Docs' }];
}

export default function NotFound() {
  return (
    <HomeLayout {...baseOptions()}>
      <div className="p-4 flex flex-col items-center justify-center text-center flex-1 my-16">
        <h1 className="text-3xl font-bold mb-2 text-fd-foreground">Page Not Found</h1>
        <p className="text-fd-muted-foreground mb-6">
          The documentation page you are looking for does not exist or may have moved.
        </p>
        <div className="flex gap-4">
          <Link
            className="text-sm bg-fd-primary text-fd-primary-foreground rounded-lg font-semibold px-4 py-2 hover:opacity-90 transition"
            to="/"
          >
            Docs Home
          </Link>
          <Link
            className="text-sm bg-fd-muted text-fd-foreground rounded-lg font-semibold px-4 py-2 hover:bg-fd-accent/20 transition"
            to="/sdk"
          >
            SDK Guide
          </Link>
        </div>
      </div>
    </HomeLayout>
  );
}
