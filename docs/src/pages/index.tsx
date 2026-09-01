import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import {DocCard, DocCardGroup} from '@parlot/docs-theme';

import styles from './index.module.css';

export default function Home(): JSX.Element {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout title={siteConfig.title} description={siteConfig.tagline}>
      <main>
        <section className={`parlot-overview-hero ${styles.hero}`}>
          <Heading as="h1">{siteConfig.title}</Heading>
          <p>
            Instrument LiveKit multi-agent sessions once, export OTLP to Parlot, and keep recording
            optional. Open-source SDK docs for builders shipping voice agents.
          </p>
          <div className="parlot-overview-actions">
            <Link className="button button--primary button--lg" to="/get-started/quick-start">
              Quick Start
            </Link>
            <Link className="button button--secondary button--lg" to="/guides">
              Browse guides
            </Link>
            <Link className="button button--secondary button--lg" to="/api">
              API Reference
            </Link>
          </div>
        </section>

        <section className="parlot-overview-section">
          <DocCardGroup columns={4}>
            <DocCard
              eyebrow="Get started"
              title="Quick Start"
              description="Install the SDK, call configure(), and export OTLP in a few minutes."
              to="/get-started/quick-start"
            />
            <DocCard
              eyebrow="Concepts"
              title="Sessions and turns"
              description="Semantic conventions for sessions, turns, handoffs, and agent identity."
              to="/get-started/concepts"
            />
            <DocCard
              eyebrow="Guides"
              title="Integrations"
              description="Checklists and guides for LiveKit and LangGraph production agents."
              to="/guides"
            />
            <DocCard
              eyebrow="Reference"
              title="API Reference"
              description="Complete Python API signatures, parameters, core helpers, and environment variables."
              to="/api"
            />
          </DocCardGroup>
        </section>
      </main>
    </Layout>
  );
}
