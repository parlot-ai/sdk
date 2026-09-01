import React from 'react';
import {
  useAllDocsData,
  useDoc,
  useCurrentSidebarSiblings,
  filterDocCardListItems,
} from '@docusaurus/plugin-content-docs/client';
import {DocCard, DocCardGroup} from './DocCard.js';

/**
 * Parlot-styled cards for the current sidebar category (sibling docs).
 * Drop-in replacement for @theme/DocCardList without single-line truncation.
 * @param {{ columns?: number }} props
 */
export function CategoryDocCardList({columns = 2}) {
  const siblings = useCurrentSidebarSiblings();
  const allDocsData = useAllDocsData();
  const {metadata: currentDoc} = useDoc();

  const docById = React.useMemo(() => {
    /** @type {Map<string, import('@docusaurus/plugin-content-docs').GlobalDoc>} */
    const map = new Map();
    for (const pluginData of Object.values(allDocsData)) {
      for (const doc of pluginData.versions[0]?.docs ?? []) {
        map.set(doc.id, doc);
      }
    }
    return map;
  }, [allDocsData]);

  const cards = React.useMemo(() => {
    const items = filterDocCardListItems(siblings ?? []);
    return items
      .map((item) => {
        if (item.type !== 'doc') {
          return null;
        }
        const docId = item.docId ?? item.id;
        if (!docId || docId === currentDoc?.id) {
          return null;
        }
        const doc = docById.get(docId);
        const customProps = doc?.frontMatter?.sidebar_custom_props ?? {};
        const eyebrow =
          typeof customProps.eyebrow === 'string' ? customProps.eyebrow : undefined;
        return {
          docId,
          title: doc?.title ?? item.label,
          description: doc?.description ?? item.description ?? '',
          eyebrow,
          to: item.href ?? doc?.permalink,
        };
      })
      .filter(Boolean);
  }, [siblings, currentDoc?.id, docById]);

  if (cards.length === 0) {
    return null;
  }

  return React.createElement(
    DocCardGroup,
    {columns},
    cards.map((card) =>
      React.createElement(DocCard, {
        key: card.docId,
        title: card.title,
        description: card.description,
        eyebrow: card.eyebrow,
        to: card.to,
      }),
    ),
  );
}
