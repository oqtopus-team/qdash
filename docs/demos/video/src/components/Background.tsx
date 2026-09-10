import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { theme } from "../theme";

/**
 * Soft lavender → pink gradient with slowly drifting blobs, echoing the
 * QDash login page background.
 */
export const Background: React.FC<{ dark?: boolean }> = ({ dark = false }) => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, 900], [0, 80]);

  const base = dark
    ? "linear-gradient(135deg, #111536 0%, #1a2150 55%, #2a1b4a 100%)"
    : "linear-gradient(135deg, #e9ecfb 0%, #f5f6fb 45%, #fbeaf1 100%)";

  return (
    <AbsoluteFill style={{ background: base, overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          width: 900,
          height: 900,
          borderRadius: "50%",
          left: -250 + drift,
          top: -350 + drift * 0.4,
          background: dark
            ? "radial-gradient(circle, rgba(59,68,224,0.50), rgba(59,68,224,0))"
            : "radial-gradient(circle, rgba(59,68,224,0.20), rgba(59,68,224,0))",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1000,
          height: 1000,
          borderRadius: "50%",
          right: -300 - drift * 0.6,
          bottom: -450 + drift * 0.3,
          background: dark
            ? "radial-gradient(circle, rgba(224,64,122,0.35), rgba(224,64,122,0))"
            : "radial-gradient(circle, rgba(224,64,122,0.16), rgba(224,64,122,0))",
        }}
      />
      {/* subtle dot grid */}
      <AbsoluteFill
        style={{
          backgroundImage: `radial-gradient(${
            dark ? "rgba(255,255,255,0.08)" : "rgba(31,26,61,0.07)"
          } 1.5px, transparent 1.5px)`,
          backgroundSize: "36px 36px",
          opacity: 0.9,
        }}
      />
      <span style={{ display: "none", color: theme.ink }} />
    </AbsoluteFill>
  );
};
