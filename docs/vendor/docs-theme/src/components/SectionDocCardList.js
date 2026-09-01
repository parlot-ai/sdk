import React from 'react';
import {useAllDocsData, useDoc, useDocsSidebar} from '@docusaurus/plugin-content-docs/client';
import {DocCard, DocCardGroup} from './DocCard.js';

/**
 * @param {import('@docusaurus/plugin-content-docs').PropSidebarItem[]} items
 * @param {string[]} excludeCategoryLabels
 * @returns {import('@docusaurus/plugin-content-docs').PropSidebarItemDoc[]}
 */
function collectDocItems(items, excludeCategoryLabels) {
  /** @type {import('@docusaurus/plugin-content-docs').PropSidebarItemDoc[]} */
  const docs = [];
  for (const item of items ?? []) {
    if (item.type === 'doc') {
      docs.push(item);
    } else if (item.type === 'category') {
      if (excludeCategoryLabels.includes(item.label)) {
        continue;
      }
      docs.push(...collectDocItems(item.items, excludeCategoryLabels));
    }
  }
  return docs;
}

/**
 * Renders Parlot DocCards for every doc in the current plugin sidebar (flattened).
 * @param {{
 *   columns?: number,
 *   excludeDocIds?: string[],
 *   excludeCategoryLabels?: string[],
 * }} props
 */
export function SectionDocCardList({
  columns = 2,
  excludeDocIds,
  excludeCategoryLabels = [],
}) {
  const sidebar = useDocsSidebar();
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

  const excludedIds = React.useMemo(() => {
    const ids = new Set(excludeDocIds ?? []);
    if (currentDoc?.id) {
      ids.add(currentDoc.id);
    }
    return ids;
  }, [excludeDocIds, currentDoc?.id]);

  const sidebarDocs = React.useMemo(
    () => collectDocItems(sidebar?.items, excludeCategoryLabels),
    [sidebar?.items, excludeCategoryLabels],
  );

  const cards = sidebarDocs
    .map((item) => {
      const docId = item.docId ?? item.id;
      if (!docId || excludedIds.has(docId)) {
        return null;
      }
      const doc = docById.get(docId);
      const customProps = doc?.frontMatter?.sidebar_custom_props ?? {};
      const eyebrow =
        typeof customProps.eyebrow === 'string' ? customProps.eyebrow : undefined;
      return {
        docId,
        title: doc?.title ?? item.label,
        description: doc?.description ?? '',
        eyebrow,
        to: item.href ?? doc?.permalink,
      };
    })
    .filter(Boolean);

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
