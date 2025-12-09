"use client";

import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";

import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { useAuth } from "@/contexts/AuthContext";

export default function LoginPage() {
  const [userName, setUserName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const router = useRouter();
  const { login: authLogin, loading } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setError("");

    try {
      await authLogin(userName, password);
      router.replace("/execution");
      window.location.href = "/execution";
    } catch (err) {
      setError("Login failed. Please check your user ID and password.");
    }
  };

  useEffect(() => {
    if (window.location.search) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-base-200 via-base-100 to-base-200">
      {loading && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <LoadingSpinner />
        </div>
      )}

      <div className="card w-full max-w-md bg-base-100 shadow-2xl mx-4">
        <div className="card-body p-8">
          {/* Logo and Title */}
          <div className="flex flex-col items-center gap-4 mb-6">
            <div className="floating-logo">
              <img
                src="/oqtopus_logo.svg"
                alt="Oqtopus Logo"
                className="w-32 h-32 object-contain"
              />
            </div>
            <div className="text-center">
              <h1 className="text-3xl font-bold text-base-content">QDash</h1>
              <p className="text-sm text-base-content/60 mt-1">
                Quantum Calibration Dashboard
              </p>
            </div>
          </div>

          {/* Login Form */}
          <form
            onSubmit={handleSubmit}
            autoComplete="off"
            className="space-y-4"
          >
            <div className="form-control">
              <label className="label" htmlFor="userName">
                <span className="label-text font-medium">User ID</span>
              </label>
              <input
                id="userName"
                name="username"
                type="text"
                required
                autoComplete="off"
                spellCheck="false"
                className="input input-bordered w-full focus:input-primary"
                placeholder="Enter your user ID"
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
              />
            </div>

            <div className="form-control">
              <label className="label" htmlFor="password">
                <span className="label-text font-medium">Password</span>
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                autoComplete="new-password"
                className="input input-bordered w-full focus:input-primary"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error && (
              <div className="alert alert-error py-2">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="stroke-current shrink-0 h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span className="text-sm">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className={`btn btn-primary w-full mt-2 ${loading ? "loading" : ""}`}
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>

          {/* Footer */}
          <div className="divider my-4"></div>
          <p className="text-center text-xs text-base-content/50">
            Contact an administrator if you need an account.
          </p>
        </div>
      </div>
    </div>
  );
}
