"use client";

import { Component } from "react";

import type { ErrorInfo, ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * Error Boundary component for catching and displaying React errors.
 * Provides a fallback UI and optional error reporting callback.
 */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="card bg-base-100 shadow-xl rounded-xl p-8 border border-error/20 m-4">
          <div className="flex flex-col items-center text-center space-y-4">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-16 h-16 text-error"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="15" y1="9" x2="9" y2="15"></line>
              <line x1="9" y1="9" x2="15" y2="15"></line>
            </svg>

            <h3 className="text-xl font-semibold text-error">
              Something went wrong
            </h3>

            <p className="text-base-content/70 max-w-md">
              An unexpected error occurred. Please try again or contact support
              if the problem persists.
            </p>

            {process.env.NODE_ENV === "development" && this.state.error && (
              <details className="text-left w-full max-w-lg">
                <summary className="cursor-pointer text-sm text-base-content/50 hover:text-base-content">
                  Show error details
                </summary>
                <pre className="mt-2 p-4 bg-base-200 rounded-lg text-xs overflow-x-auto text-error">
                  {this.state.error.message}
                  {"\n\n"}
                  {this.state.error.stack}
                </pre>
              </details>
            )}

            <div className="card-actions gap-2">
              <button
                className="btn btn-error btn-outline gap-2"
                onClick={this.handleRetry}
                type="button"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <polyline points="23 4 23 10 17 10"></polyline>
                  <polyline points="1 20 1 14 7 14"></polyline>
                  <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path>
                </svg>
                Try Again
              </button>
              <button
                className="btn btn-ghost gap-2"
                onClick={() => window.location.reload()}
                type="button"
              >
                Reload Page
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
