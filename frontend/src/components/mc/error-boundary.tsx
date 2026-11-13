"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorState } from "@/components/data/states";

/**
 * Keeps one failing panel from taking down the whole page. The fallback names the panel and
 * offers a retry that remounts it.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode; label?: string; className?: string },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Panel failed to render${this.props.label ? ` (${this.props.label})` : ""}`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <ErrorState
          className={this.props.className}
          title={`${this.props.label ?? "This panel"} failed to render`}
          error={this.state.error}
          onRetry={() => this.setState({ error: null })}
        />
      );
    }
    return this.props.children;
  }
}
