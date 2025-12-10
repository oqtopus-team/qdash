"use client";

import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";

import { EnvironmentBadge } from "@/components/ui/EnvironmentBadge";
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
    <div className="hero login-page-bg min-h-screen items-start pt-12 sm:pt-0 sm:items-center">
      {loading && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <LoadingSpinner />
        </div>
      )}

      <div className="hero-content flex-col lg:flex-row gap-6 lg:gap-16 px-4">
        {/* Left side - Logo and description */}
        <div className="text-center lg:text-left max-w-lg">
          <div className="floating-logo inline-block mb-8">
            <img
              src="/oqtopus_logo.svg"
              alt="Oqtopus Logo"
              className="w-40 h-40 lg:w-52 lg:h-52 object-contain"
            />
          </div>
          <h1 className="text-5xl lg:text-6xl font-bold login-title-gradient">
            QDash
          </h1>
          <div className="mt-4">
            <EnvironmentBadge className="badge-lg" />
          </div>
          <p className="py-6 text-base-content/70 text-xl lg:text-2xl">
            Quantum Calibration Dashboard for managing and monitoring qubit
            calibration workflows.
          </p>
          <div className="hidden lg:flex gap-3 flex-wrap">
            <span className="badge badge-outline badge-lg">Calibration</span>
            <span className="badge badge-outline badge-lg">Monitoring</span>
            <span className="badge badge-outline badge-lg">Workflow</span>
          </div>
        </div>

        {/* Right side - Login form */}
        <div className="card bg-base-100/95 backdrop-blur-sm w-full max-w-sm shadow-2xl border border-base-300">
          <div className="card-body">
            <h2 className="card-title text-xl mb-2">Sign In</h2>
            <form onSubmit={handleSubmit} autoComplete="off">
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

              <div className="form-control mt-3">
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
                <div className="alert alert-error py-2 mt-4">
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
                className={`btn btn-primary btn-glow w-full mt-6 ${loading ? "loading" : ""}`}
              >
                {loading ? "Signing in..." : "Sign In"}
              </button>
            </form>

            <p className="text-center text-xs text-base-content/50 mt-4">
              Contact an administrator if you need an account.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
