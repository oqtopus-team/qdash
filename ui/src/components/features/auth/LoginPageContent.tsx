"use client";

import Image from "next/image";
import { useCallback, useEffect, useState } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, BookOpen, Eye, EyeOff, GitBranch, Loader2, Moon, Sun } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { EnvironmentBadge } from "@/components/ui/EnvironmentBadge";
import { DARK_THEMES } from "@/constants/themes";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import { navigateTo } from "@/lib/navigation";

const loginSchema = z.object({
  username: z.string().trim().min(1, "User ID is required"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormData = z.infer<typeof loginSchema>;

/** Joins the truthy ids into an aria-describedby value, or undefined when none apply. */
function describedBy(...ids: (string | false | undefined)[]) {
  return ids.filter(Boolean).join(" ") || undefined;
}

/** Renders the sign-in page with a schema-validated login form. */
export function LoginPageContent() {
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  });
  const { login: authLogin, loading } = useAuth();
  const { theme, setTheme } = useTheme();

  const isDarkTheme = DARK_THEMES.includes(theme);

  const toggleTheme = useCallback(() => {
    setTheme(isDarkTheme ? "light" : "dark");
  }, [isDarkTheme, setTheme]);

  /** Clears any stale submission error, then validates and submits the form. */
  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    setError("");
    return handleSubmit(submit)(event);
  };

  /** Logs in with the validated values and redirects, or records a submission error. */
  const submit = async (values: LoginFormData) => {
    try {
      await authLogin(values.username, values.password);
      navigateTo("/execution");
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
    <main className="grid min-h-dvh grid-rows-[auto_1fr] bg-base-100 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:grid-rows-1 lg:p-3">
      <section
        aria-label="QDash"
        className="relative isolate flex flex-col overflow-hidden bg-base-200 px-5 pb-8 pt-4 sm:px-8 sm:pb-10 lg:justify-between lg:rounded-box lg:p-10 xl:p-12"
      >
        {/* Brand field: the logo's own blue and red, diffused into two static soft forms. */}
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
          <div className="absolute -left-20 -top-28 h-64 w-80 rounded-full bg-[#1f1fdd]/35 blur-3xl sm:-left-24 sm:h-72 sm:w-[28rem] lg:-left-[15%] lg:top-[10%] lg:h-[60%] lg:w-[75%]" />
          <div className="absolute -bottom-32 -right-16 h-64 w-72 rounded-full bg-[#e21331]/30 blur-3xl sm:-right-20 sm:h-72 sm:w-96 lg:-right-[20%] lg:bottom-[-15%] lg:h-[65%] lg:w-[70%]" />
          <div className="absolute right-[10%] top-[-20%] hidden h-[40%] w-[40%] rounded-full bg-[#1f1fdd]/20 blur-3xl lg:block" />
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="text-xl font-medium">QDash</h1>
            {/* Operational context, not decoration: stays legible and wraps rather than overflows. */}
            <EnvironmentBadge className="badge-md h-auto min-h-0 max-w-full whitespace-normal break-all py-1 text-left" />
          </div>
          <button
            type="button"
            onClick={toggleTheme}
            className="btn btn-ghost btn-sm btn-square shrink-0 text-base-content/70 hover:text-base-content"
            aria-label={`Switch to ${isDarkTheme ? "light" : "dark"} theme`}
          >
            {isDarkTheme ? (
              <Sun size={18} aria-hidden="true" />
            ) : (
              <Moon size={18} aria-hidden="true" />
            )}
          </button>
        </div>

        {/* Same composition at every width: tagline left, logo right, bottom aligned. */}
        <div className="mt-6 grid gap-6 sm:mt-8 lg:mt-0 lg:flex-1 lg:grid-rows-[1fr_auto] lg:gap-10 lg:pt-16">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-5 sm:gap-8">
            <p className="max-w-[16rem] text-lg font-medium leading-snug tracking-tight sm:max-w-sm sm:text-2xl lg:text-3xl lg:leading-tight xl:text-4xl">
              Calibration workflows for superconducting qubit chips
            </p>
            <Image
              src="/oqtopus_logo.svg"
              alt="Oqtopus"
              width={320}
              height={320}
              preload
              className="h-16 w-16 object-contain sm:h-24 sm:w-24 lg:h-40 lg:w-40 xl:h-52 xl:w-52"
            />
          </div>
          <div className="hidden text-xs text-base-content/60 lg:block">
            <p className="font-medium text-base-content/80">OQTOPUS</p>
            <p>Open Quantum Toolchain for OPerators and USers</p>
          </div>
        </div>
      </section>

      <section
        aria-labelledby="sign-in-heading"
        className="flex flex-col px-5 pb-10 pt-8 sm:px-10 sm:pt-10 lg:grid lg:grid-rows-[1fr_auto_1fr] lg:px-16 lg:py-10"
      >
        <div className="mx-auto w-full max-w-[380px] lg:row-start-2">
          <h2 id="sign-in-heading" className="text-xl font-medium">
            Sign in
          </h2>

          {/* Each credential is one row: the label sits inside the field so the pair reads as a
              single surface instead of a stacked label, box and helper line. */}
          <form onSubmit={onSubmit} className="mt-6" aria-busy={loading} noValidate>
            <fieldset disabled={loading} className="flex flex-col gap-3">
              <div>
                <label
                  htmlFor="userName"
                  className={`input w-full focus-within:input-primary ${errors.username ? "input-error" : ""}`}
                >
                  <span className="label w-22 shrink-0 border-e-0">User ID</span>
                  <input
                    id="userName"
                    type="text"
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck="false"
                    autoFocus
                    className="min-w-0"
                    aria-required="true"
                    aria-invalid={Boolean(errors.username)}
                    aria-describedby={describedBy(errors.username?.message && "userName-error")}
                    {...register("username")}
                  />
                </label>
                {errors.username && (
                  <p id="userName-error" className="mt-1.5 text-sm text-error">
                    {errors.username.message}
                  </p>
                )}
              </div>

              <div>
                <div className="relative">
                  <label
                    htmlFor="password"
                    className={`input w-full pr-12 focus-within:input-primary ${errors.password ? "input-error" : ""}`}
                  >
                    <span className="label w-22 shrink-0 border-e-0">Password</span>
                    <input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      className="min-w-0"
                      aria-required="true"
                      aria-invalid={Boolean(errors.password)}
                      aria-describedby={describedBy(
                        errors.password?.message && "password-error",
                        error && "login-error",
                      )}
                      {...register("password")}
                    />
                  </label>
                  {/* Outside the label so a click toggles visibility without also activating the field. */}
                  <button
                    type="button"
                    onClick={() => setShowPassword((visible) => !visible)}
                    className="btn btn-ghost btn-sm btn-square absolute right-1 top-1/2 -translate-y-1/2 text-base-content/60 hover:text-base-content"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? (
                      <EyeOff size={18} aria-hidden="true" />
                    ) : (
                      <Eye size={18} aria-hidden="true" />
                    )}
                  </button>
                </div>
                {errors.password && (
                  <p id="password-error" className="mt-1.5 text-sm text-error">
                    {errors.password.message}
                  </p>
                )}
              </div>
            </fieldset>

            {error && (
              <div id="login-error" role="alert" className="alert alert-error alert-soft mt-4 py-3">
                <AlertCircle size={20} className="shrink-0" aria-hidden="true" />
                <span className="text-sm">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || isSubmitting}
              className="btn btn-primary mt-5 w-full"
            >
              {loading && <Loader2 size={18} className="animate-spin" aria-hidden="true" />}
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <nav
          aria-label="QDash resources"
          className="mx-auto mt-auto flex w-full max-w-[380px] items-center gap-x-5 pt-12 text-xs text-base-content/60 lg:row-start-3 lg:self-end lg:pt-0"
        >
          <a
            href="https://oqtopus-team.github.io/qdash/"
            target="_blank"
            rel="noopener noreferrer"
            className="link link-hover inline-flex items-center gap-1.5 hover:text-base-content"
          >
            <BookOpen size={16} aria-hidden="true" />
            Docs
          </a>
          <a
            href="https://github.com/oqtopus-team/qdash"
            target="_blank"
            rel="noopener noreferrer"
            className="link link-hover inline-flex items-center gap-1.5 hover:text-base-content"
          >
            <GitBranch size={16} aria-hidden="true" />
            GitHub
          </a>
        </nav>
      </section>
    </main>
  );
}
