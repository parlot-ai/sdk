import {
  acceptDocsAnalytics,
  rejectDocsAnalytics,
} from '@/lib/posthog';

export function CookieConsentBanner({
  visible,
  onDismiss,
}: {
  visible: boolean;
  onDismiss: () => void;
}) {
  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-label="Cookie consent"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-fd-border bg-fd-background/95 p-4 shadow-lg backdrop-blur-md"
    >
      <div className="mx-auto flex max-w-5xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
        <p className="text-sm text-fd-muted-foreground">
          Optional analytics cookies help us see which docs help developers get
          Parlot working. We only use them if you say yes.{' '}
          <a
            href="https://parlot.ai/privacy"
            className="underline underline-offset-2"
          >
            Privacy
          </a>
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            className="rounded-md px-3 py-1.5 text-sm text-fd-muted-foreground hover:bg-fd-accent hover:text-fd-accent-foreground"
            onClick={() => {
              rejectDocsAnalytics();
              onDismiss();
            }}
          >
            No thanks
          </button>
          <button
            type="button"
            className="rounded-md bg-fd-primary px-3 py-1.5 text-sm text-fd-primary-foreground"
            onClick={() => {
              acceptDocsAnalytics();
              onDismiss();
            }}
          >
            Accept analytics
          </button>
        </div>
      </div>
    </div>
  );
}
