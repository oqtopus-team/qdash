import Link from "next/link";

import { GoBackButton } from "@/components/ui/GoBackButton";

export default function NotFound() {
  return (
    <div className="hero login-page-bg min-h-screen">
      <div className="hero-content flex-col text-center px-4">
        {/* Logo with lost animation */}
        <div className="not-found-logo mb-6">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/oqtopus_logo.svg"
            alt="Oqtopus Logo"
            className="w-32 h-32 lg:w-40 lg:h-40 object-contain opacity-60"
          />
        </div>

        {/* 404 Number */}
        <h1 className="text-8xl lg:text-9xl font-bold login-title-gradient tracking-tight">
          404
        </h1>

        {/* Message */}
        <h2 className="text-2xl lg:text-3xl font-semibold text-base-content mt-4">
          Page Not Found
        </h2>
        <p className="text-base-content/60 text-lg max-w-md mt-2">
          The quantum state you&apos;re looking for seems to have collapsed into
          a different dimension.
        </p>

        {/* Action buttons */}
        <div className="flex flex-col sm:flex-row gap-4 mt-8">
          <Link href="/" className="btn btn-primary btn-glow px-8">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5 mr-2"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
              />
            </svg>
            Back to Home
          </Link>
          <GoBackButton />
        </div>

        {/* Decorative elements */}
        <div className="mt-12 flex gap-2">
          <span className="badge badge-outline badge-lg opacity-50">
            Lost in superposition
          </span>
        </div>
      </div>
    </div>
  );
}
