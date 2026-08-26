"use client";

import Image from "next/image";
import { useCallback, useEffect, useState } from "react";

import { AlertCircle, BookOpen, Eye, EyeOff, GitBranch, Loader2, Moon, Sun } from "lucide-react";

import { EnvironmentBadge } from "@/components/ui/EnvironmentBadge";
import { DARK_THEMES } from "@/constants/themes";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";

export function LoginPageContent() {
  const [userName, setUserName] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const { login: authLogin, loading } = useAuth();
  const { theme, setTheme } = useTheme();

  const isDarkTheme = DARK_THEMES.includes(theme);

  const toggleTheme = useCallback(() => {
    setTheme(isDarkTheme ? "light" : "dark");
  }, [isDarkTheme, setTheme]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");

    try {
      await authLogin(userName, password);
      window.location.href = "/execution";
    } catch {
      setError("Login failed. Please check your user ID and password.");
    }
  };

  useEffect(() => {
    if (window.location.search) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  return (
    <main className="login-page-bg min-h-dvh overflow-x-hidden px-4 py-8 sm:px-6 lg:px-8">
      <div className="relative z-10 mx-auto grid min-h-[calc(100dvh-4rem)] w-full max-w-6xl items-center gap-10 lg:grid-cols-[minmax(0,1fr)_24rem] lg:gap-16">
        <section className="mx-auto max-w-xl text-center lg:mx-0 lg:text-left">
          <Image
            src="/oqtopus_logo.svg"
            alt="Oqtopus"
            width={176}
            height={176}
            priority
            className="floating-logo mx-auto h-28 w-28 object-contain sm:h-36 sm:w-36 lg:mx-0 lg:h-44 lg:w-44"
          />

          <div className="mt-5 flex flex-wrap items-center justify-center gap-3 lg:justify-start">
            <h1 className="login-title-gradient text-5xl font-bold tracking-tight sm:text-6xl">
              QDash
            </h1>
            <EnvironmentBadge className="badge-lg" />
          </div>

          <p className="mx-auto mt-5 max-w-lg text-lg leading-relaxed text-base-content/70 sm:text-xl lg:mx-0">
            Manage and monitor qubit calibration workflows from one focused dashboard.
          </p>

          <nav
            aria-label="QDash resources"
            className="mt-6 flex flex-wrap justify-center gap-2 lg:justify-start"
          >
            <a
              href="https://oqtopus-team.github.io/qdash/"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-ghost btn-sm gap-2"
            >
              <BookOpen size={18} aria-hidden="true" />
              Docs
            </a>
            <a
              href="https://github.com/oqtopus-team/qdash"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-ghost btn-sm gap-2"
            >
              <GitBranch size={18} aria-hidden="true" />
              GitHub
            </a>
            <button
              type="button"
              onClick={toggleTheme}
              className="btn btn-ghost btn-sm gap-2"
              aria-label={`Switch to ${isDarkTheme ? "light" : "dark"} theme`}
            >
              {isDarkTheme ? (
                <Sun size={18} aria-hidden="true" />
              ) : (
                <Moon size={18} aria-hidden="true" />
              )}
              {isDarkTheme ? "Light" : "Dark"}
            </button>
          </nav>
        </section>

        <section
          aria-labelledby="sign-in-heading"
          className="card mx-auto w-full max-w-sm border border-base-300 bg-base-100/95 shadow-2xl backdrop-blur-sm"
        >
          <div className="card-body gap-0 p-6 sm:p-8">
            <h2 id="sign-in-heading" className="text-2xl font-semibold tracking-tight">
              Welcome back
            </h2>
            <p className="mt-1 text-sm text-base-content/60">Sign in to continue to QDash.</p>

            <form onSubmit={handleSubmit} className="mt-6" aria-busy={loading}>
              <fieldset disabled={loading} className="contents">
                <div className="form-control">
                  <label className="label" htmlFor="userName">
                    <span className="label-text font-medium">User ID</span>
                  </label>
                  <input
                    id="userName"
                    name="username"
                    type="text"
                    required
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck="false"
                    autoFocus
                    className="input input-bordered w-full focus:input-primary"
                    placeholder="Enter your user ID"
                    value={userName}
                    onChange={(event) => setUserName(event.target.value)}
                  />
                </div>

                <div className="form-control mt-3">
                  <label className="label" htmlFor="password">
                    <span className="label-text font-medium">Password</span>
                  </label>
                  <div className="relative">
                    <input
                      id="password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      required
                      autoComplete="current-password"
                      className="input input-bordered w-full pr-12 focus:input-primary"
                      placeholder="Enter your password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      aria-describedby={error ? "login-error" : undefined}
                    />
                    <span className="absolute right-1 top-1/2 -translate-y-1/2">
                      <button
                        type="button"
                        onClick={() => setShowPassword((visible) => !visible)}
                        className="btn btn-ghost btn-sm btn-square"
                        aria-label={showPassword ? "Hide password" : "Show password"}
                      >
                        {showPassword ? (
                          <EyeOff size={18} aria-hidden="true" />
                        ) : (
                          <Eye size={18} aria-hidden="true" />
                        )}
                      </button>
                    </span>
                  </div>
                </div>
              </fieldset>

              {error && (
                <div id="login-error" role="alert" className="alert alert-error mt-4 py-3">
                  <AlertCircle size={20} className="shrink-0" aria-hidden="true" />
                  <span className="text-sm">{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="btn btn-primary btn-glow mt-6 w-full"
              >
                {loading && <Loader2 size={18} className="animate-spin" aria-hidden="true" />}
                {loading ? "Signing in…" : "Sign in"}
              </button>
            </form>

            <p className="mt-5 text-center text-xs text-base-content/50">
              Need access? Contact your QDash administrator.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
