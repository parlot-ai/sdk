import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';

const THEMES = [
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
  { id: 'system', label: 'System', icon: Monitor },
] as const;

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const currentTheme = mounted ? (theme || 'system') : 'system';

  return (
    <div
      className={
        'inline-flex items-center rounded-full border border-fd-border p-0.5 bg-fd-secondary/50 ' +
        (className || '')
      }
      role="radiogroup"
      aria-label="Theme preference"
    >
      {THEMES.map(({ id, label, icon: Icon }) => {
        const isActive = currentTheme === id;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={isActive}
            aria-label={`${label} theme`}
            title={`${label} theme`}
            onClick={() => setTheme(id)}
            className={`p-1.5 rounded-full transition-colors cursor-pointer ${
              isActive
                ? 'bg-fd-accent text-fd-accent-foreground shadow-xs'
                : 'text-fd-muted-foreground hover:text-fd-foreground'
            }`}
          >
            <Icon className="size-3.5" fill={isActive && id !== 'system' ? 'currentColor' : 'none'} />
          </button>
        );
      })}
    </div>
  );
}

export default ThemeToggle;
