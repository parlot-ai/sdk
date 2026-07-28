import React from 'react';
import Link from '@docusaurus/Link';

/**
 * Feature / navigation card used on overview pages.
 * @param {{
 *   title: string,
 *   description?: string,
 *   to?: string,
 *   href?: string,
 *   eyebrow?: string,
 *   children?: React.ReactNode,
 * }} props
 */
export function DocCard({ title, description, to, href, eyebrow, children }) {
  const className = 'parlot-card';
  const body = [
    eyebrow
      ? React.createElement('span', {key: 'eyebrow', className: 'parlot-card__eyebrow'}, eyebrow)
      : null,
    React.createElement('h3', {key: 'title', className: 'parlot-card__title'}, title),
    description
      ? React.createElement(
          'p',
          {key: 'description', className: 'parlot-card__description'},
          description,
        )
      : null,
    children,
  ];

  if (to) {
    return React.createElement(Link, {className, to}, body);
  }

  if (href) {
    return React.createElement(
      'a',
      {className, href, target: '_blank', rel: 'noreferrer'},
      body,
    );
  }

  return React.createElement('div', {className}, body);
}

/**
 * Responsive grid wrapper for DocCard.
 * @param {{ children: React.ReactNode, columns?: number }} props
 */
export function DocCardGroup({ children, columns }) {
  const style = columns
    ? {gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`}
    : undefined;
  return React.createElement('div', {className: 'parlot-card-grid', style}, children);
}
