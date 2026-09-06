import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { appName, gitConfig } from './shared';
import { ThemeToggle } from '@/components/theme-toggle';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <div className="flex items-center gap-2.5 font-semibold text-fd-foreground">
          <img
            src="/docs/img/logo.webp"
            alt="Parlot"
            className="size-7 shrink-0 rounded-md object-contain dark:border dark:border-white/20 dark:bg-slate-50 dark:p-0.5"
          />
          <span>{appName}</span>
        </div>
      ),
    },
    githubUrl: `https://github.com/${gitConfig.user}/${gitConfig.repo}`,
    slots: {
      themeSwitch: ThemeToggle,
    },
  };
}
