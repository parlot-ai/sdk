import React from 'react';
import Link from '@docusaurus/Link';
import {useLocation} from '@docusaurus/router';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import clsx from 'clsx';

/**
 * @typedef {{ label: string, to: string, match?: string }} SectionNavItem
 */

/**
 * Second-row product/section tabs (ElevenLabs-style header).
 * Reads items from `siteConfig.customFields.sectionNav`.
 */
export function SectionNav() {
  const {siteConfig} = useDocusaurusContext();
  const location = useLocation();
  /** @type {SectionNavItem[]} */
  const items = siteConfig.customFields?.sectionNav ?? [];

  if (!items.length) {
    return null;
  }

  return React.createElement(
    'div',
    {
      className: 'parlot-section-nav',
      role: 'navigation',
      'aria-label': 'Documentation sections',
    },
    items.map((item) => {
      const active = isActive(location.pathname, item);
      return React.createElement(
        Link,
        {
          key: item.to,
          to: item.to,
          className: clsx(
            'parlot-section-nav__link',
            active && 'parlot-section-nav__link--active',
          ),
          'aria-current': active ? 'page' : undefined,
        },
        item.label,
      );
    }),
  );
}

/**
 * @param {string} pathname
 * @param {SectionNavItem} item
 */
function isActive(pathname, item) {
  const target = item.match ?? item.to;
  if (target === '/' || target === '') {
    return pathname === '/' || pathname === '';
  }
  return pathname === target || pathname.startsWith(`${target}/`);
}
