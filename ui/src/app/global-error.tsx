"use client";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen flex items-center justify-center bg-gray-100">
          <div className="text-center px-4">
            <div className="mb-6 opacity-60">
              <img
                src="/oqtopus_logo.svg"
                alt="Oqtopus Logo"
                className="w-32 h-32 mx-auto"
              />
            </div>

            <h1 className="text-3xl font-bold text-gray-800 mb-4">
              Something went wrong
            </h1>

            <p className="text-gray-600 text-lg max-w-md mx-auto mb-8">
              An unexpected error occurred. Please try again.
            </p>

            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <button
                onClick={reset}
                className="px-8 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Try Again
              </button>
              <button
                onClick={() => (window.location.href = "/")}
                className="px-8 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Back to Home
              </button>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
