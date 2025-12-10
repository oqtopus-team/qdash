"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Application error:", error);
  }, [error]);

  return (
    <div className="hero login-page-bg min-h-screen">
      <div className="hero-content flex-col text-center px-4">
        <div className="mb-6 opacity-60">
          <img
            src="/oqtopus_logo.svg"
            alt="Oqtopus Logo"
            className="w-32 h-32 lg:w-40 lg:h-40 object-contain"
          />
        </div>

        <div className="text-error mb-4">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-16 h-16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y1="9" x2="9" y2="15"></line>
            <line x1="9" y1="9" x2="15" y2="15"></line>
          </svg>
        </div>

        <h1 className="text-3xl lg:text-4xl font-bold text-base-content">
          Something went wrong
        </h1>

        <p className="text-base-content/60 text-lg max-w-md mt-2">
          An unexpected error occurred. Please try again or contact support if
          the problem persists.
        </p>

        <div className="flex flex-col sm:flex-row gap-4 mt-8">
          <button onClick={reset} className="btn btn-primary btn-glow px-8">
            Try Again
          </button>
          <Link href="/" className="btn btn-outline btn-primary px-8">
            Back to Home
          </Link>
        </div>
      </div>
    </div>
  );
}
