import type { Route } from './+types/home';
import { HomeLayout } from 'fumadocs-ui/layouts/home';
import { Link } from 'react-router';
import { baseOptions } from '@/lib/layout.shared';
import { BookOpen, Code2, Terminal, Layers, ArrowRight } from 'lucide-react';

export function meta({}: Route.MetaArgs) {
  return [
    { title: 'Parlot Documentation — Observability for Voice AI' },
    {
      name: 'description',
      content:
        'Documentation for Parlot voice AI observability: SDK guides, LiveKit & LangGraph instrumentation, App user guide, and Python API reference.',
    },
  ];
}

export default function Home() {
  return (
    <HomeLayout {...baseOptions()}>
      <div className="flex-1 flex flex-col items-center justify-center text-center px-4 py-16 max-w-5xl mx-auto w-full">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-fd-primary/10 text-fd-primary mb-6">
          <span>Voice AI Observability</span>
        </div>

        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-fd-foreground mb-4">
          Parlot Documentation
        </h1>

        <p className="text-lg text-fd-muted-foreground max-w-2xl mb-8 leading-relaxed">
          Instrument LiveKit multi-agent sessions, analyze audio and turn-by-turn latency,
          and configure conversation boundaries with production-grade observability.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-4 mb-14">
          <Link
            to="/sdk/get-started/quick-start"
            className="inline-flex items-center gap-2 text-sm bg-fd-primary text-fd-primary-foreground font-semibold px-5 py-2.5 rounded-lg shadow-sm hover:opacity-90 transition"
          >
            Quick Start <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            to="/sdk"
            className="inline-flex items-center gap-2 text-sm bg-fd-muted text-fd-foreground font-medium px-5 py-2.5 rounded-lg hover:bg-fd-accent/20 transition"
          >
            SDK Guides
          </Link>
          <Link
            to="/app"
            className="inline-flex items-center gap-2 text-sm bg-fd-muted text-fd-foreground font-medium px-5 py-2.5 rounded-lg hover:bg-fd-accent/20 transition"
          >
            App Guide
          </Link>
          <a
            href="/docs/ref/python/"
            className="inline-flex items-center gap-2 text-sm bg-fd-muted text-fd-foreground font-medium px-5 py-2.5 rounded-lg hover:bg-fd-accent/20 transition"
          >
            Python API
          </a>
        </div>

        <div className="w-full text-left">
          <h2 className="text-xl font-bold mb-4 text-fd-foreground">Explore Documentation</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Link
              to="/sdk/get-started/quick-start"
              className="p-5 rounded-xl border border-fd-border bg-fd-card hover:border-fd-primary/50 transition flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center gap-2 text-fd-primary font-semibold text-sm mb-1">
                  <Terminal className="w-4 h-4" /> Get Started
                </div>
                <h3 className="text-lg font-bold text-fd-foreground mb-1">SDK Quick Start</h3>
                <p className="text-sm text-fd-muted-foreground">
                  Install parlot, call configure(), and export OpenTelemetry traces and metrics.
                </p>
              </div>
            </Link>

            <Link
              to="/sdk/guides/livekit"
              className="p-5 rounded-xl border border-fd-border bg-fd-card hover:border-fd-primary/50 transition flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center gap-2 text-fd-primary font-semibold text-sm mb-1">
                  <Layers className="w-4 h-4" /> Integrations
                </div>
                <h3 className="text-lg font-bold text-fd-foreground mb-1">LiveKit Voice Agents</h3>
                <p className="text-sm text-fd-muted-foreground">
                  Auto-instrument LiveKit agents with room session tracking, speech turns, and audio correlation.
                </p>
              </div>
            </Link>

            <Link
              to="/app"
              className="p-5 rounded-xl border border-fd-border bg-fd-card hover:border-fd-primary/50 transition flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center gap-2 text-fd-primary font-semibold text-sm mb-1">
                  <BookOpen className="w-4 h-4" /> App Guide
                </div>
                <h3 className="text-lg font-bold text-fd-foreground mb-1">Parlot Dashboard</h3>
                <p className="text-sm text-fd-muted-foreground">
                  Understand session boundaries, run evaluations, manage API keys, and inspect voice metrics.
                </p>
              </div>
            </Link>

            <a
              href="/docs/ref/python/"
              className="p-5 rounded-xl border border-fd-border bg-fd-card hover:border-fd-primary/50 transition flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center gap-2 text-fd-primary font-semibold text-sm mb-1">
                  <Code2 className="w-4 h-4" /> API Reference
                </div>
                <h3 className="text-lg font-bold text-fd-foreground mb-1">Python Reference (pdoc)</h3>
                <p className="text-sm text-fd-muted-foreground">
                  Static Google-style docstrings, classes, methods, and types generated with pdoc.
                </p>
              </div>
            </a>
          </div>
        </div>
      </div>
    </HomeLayout>
  );
}
