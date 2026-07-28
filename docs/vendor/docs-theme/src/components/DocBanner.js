import React from 'react';

/**
 * Lightweight status / audience banner for MDX pages.
 * @param {{ children: React.ReactNode, tone?: 'info' | 'warn' | 'private' | 'success' }} props
 */
export function DocBanner({ children, tone = 'info' }) {
  const toneClass =
    tone === 'warn'
      ? 'parlot-banner--warn'
      : tone === 'private'
        ? 'parlot-banner--private'
        : tone === 'success'
          ? 'parlot-banner--success'
          : '';

  return React.createElement(
    'aside',
    {className: `parlot-banner ${toneClass}`.trim()},
    children,
  );
}
