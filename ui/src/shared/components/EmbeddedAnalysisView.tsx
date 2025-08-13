import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { IoAnalytics, IoExpand } from "react-icons/io5";

interface EmbeddedAnalysisViewProps {
  title: string;
  icon?: ReactNode;
  navigateTo: string;
  height?: string;
  children: ReactNode;
  isLoading?: boolean;
}

/**
 * Wrapper component for embedding analysis views in dashboard
 * Provides consistent styling, navigation, and size controls
 */
export function EmbeddedAnalysisView({
  title,
  icon,
  navigateTo,
  height = "400px",
  children,
  isLoading = false,
}: EmbeddedAnalysisViewProps) {
  const router = useRouter();

  const handleNavigate = () => {
    router.push(navigateTo);
  };

  const handleExpandClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click when clicking expand
    handleNavigate();
  };

  return (
    <div className="card bg-base-100 shadow-xl rounded-xl border border-base-300">
      {/* Header */}
      <div className="card-header flex items-center justify-between p-4 pb-2 border-b border-base-300">
        <div className="flex items-center gap-2">
          {icon && <div className="text-primary">{icon}</div>}
          <h3 className="text-lg font-semibold">{title}</h3>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExpandClick}
            className="btn btn-sm btn-ghost btn-circle hover:btn-primary"
            title="Open full analysis"
          >
            <IoExpand className="text-base" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="card-body p-0 overflow-hidden" style={{ height }}>
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <span className="loading loading-spinner loading-lg text-primary"></span>
          </div>
        ) : (
          <div className="w-full h-full overflow-auto" onClick={handleNavigate}>
            <div
              className="transform-gpu transition-transform hover:scale-[1.02] cursor-pointer"
              style={{
                transformOrigin: "top left",
                width: "100%",
                minHeight: "100%",
              }}
            >
              {children}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="card-footer p-3 pt-2 border-t border-base-300 bg-base-50">
        <div className="flex items-center justify-between w-full">
          <div className="text-xs text-base-content/60">
            Click to expand for detailed analysis
          </div>
          <div className="flex items-center gap-1 text-xs text-primary">
            <IoAnalytics />
            <span>Analysis</span>
          </div>
        </div>
      </div>
    </div>
  );
}

interface CompactAnalysisViewProps {
  title: string;
  icon?: ReactNode;
  navigateTo: string;
  height?: string;
  children: ReactNode;
  isLoading?: boolean;
}

/**
 * Compact version without header/footer for more space efficiency
 */
export function CompactAnalysisView({
  title,
  icon,
  navigateTo,
  height = "300px",
  children,
  isLoading = false,
}: CompactAnalysisViewProps) {
  const router = useRouter();

  const handleNavigate = () => {
    router.push(navigateTo);
  };

  return (
    <div className="relative group cursor-pointer" onClick={handleNavigate}>
      <div className="card bg-base-100 shadow-xl rounded-xl border border-base-300 hover:shadow-2xl hover:border-primary/30 transition-all duration-200">
        <div className="card-body p-2 overflow-hidden" style={{ height }}>
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <span className="loading loading-spinner loading-md text-primary"></span>
            </div>
          ) : (
            <div className="w-full h-full overflow-hidden relative">
              <div
                className="transform-gpu transition-transform group-hover:scale-[1.02]"
                style={{
                  transformOrigin: "top left",
                  width: "100%",
                  minHeight: "100%",
                }}
              >
                {children}
              </div>

              {/* Overlay with title */}
              <div className="absolute inset-0 bg-gradient-to-t from-black/20 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between text-white">
                  <div className="flex items-center gap-1">
                    {icon && <div className="text-sm">{icon}</div>}
                    <span className="text-sm font-medium">{title}</span>
                  </div>
                  <IoExpand className="text-sm" />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
