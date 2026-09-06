import defaultMdxComponents from 'fumadocs-ui/mdx';
import type { MDXComponents } from 'mdx/types';
import { Callout } from 'fumadocs-ui/components/callout';
import { Tab, Tabs } from 'fumadocs-ui/components/tabs';
import { Card, Cards } from 'fumadocs-ui/components/card';
import { TypeTable } from 'fumadocs-ui/components/type-table';
import CustomLink from '@/components/link';

export function getMDXComponents(components?: MDXComponents) {
  return {
    ...defaultMdxComponents,
    a: CustomLink,
    h1: () => null,
    Callout,
    Tab,
    Tabs,
    Card,
    Cards,
    DocCard: Card,
    DocCardGroup: Cards,
    DocBanner: Callout,
    TabItem: Tab,
    TypeTable,
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
