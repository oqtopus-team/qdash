import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { theme } from "../theme";

type Props = {
  src: string;
  url: string;
  width: number;
  /** Ken Burns: start/end scale and focal point (0..1) of the screenshot. */
  zoomFrom?: number;
  zoomTo?: number;
  focusX?: number;
  focusY?: number;
  durationInFrames: number;
};

/**
 * A minimal macOS-style browser chrome around a screenshot, with a slow
 * zoom/pan so the still image feels alive.
 */
export const BrowserFrame: React.FC<Props> = ({
  src,
  url,
  width,
  zoomFrom = 1,
  zoomTo = 1.14,
  focusX = 0.5,
  focusY = 0.5,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, durationInFrames], [zoomFrom, zoomTo], {
    extrapolateRight: "clamp",
  });
  // Screenshots are 3840x1612 (viewport 1920x806 @2x).
  const aspect = 3840 / 1612;
  const height = width / aspect;

  return (
    <div
      style={{
        width,
        borderRadius: 18,
        overflow: "hidden",
        background: theme.white,
        boxShadow:
          "0 40px 90px rgba(31,26,61,0.28), 0 0 0 1px rgba(31,26,61,0.06)",
      }}
    >
      <div
        style={{
          height: 46,
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "0 18px",
          background: "#eef0f8",
          borderBottom: "1px solid rgba(31,26,61,0.08)",
        }}
      >
        {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
          <div
            key={c}
            style={{ width: 13, height: 13, borderRadius: "50%", background: c }}
          />
        ))}
        <div
          style={{
            marginLeft: 18,
            flex: 1,
            height: 28,
            borderRadius: 8,
            background: theme.white,
            display: "flex",
            alignItems: "center",
            padding: "0 14px",
            fontSize: 15,
            color: theme.inkMuted,
            fontFamily: "ui-monospace, Menlo, monospace",
            border: "1px solid rgba(31,26,61,0.08)",
          }}
        >
          {url}
        </div>
      </div>
      <div style={{ width, height, overflow: "hidden", position: "relative" }}>
        <Img
          src={staticFile(src)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${scale})`,
            transformOrigin: `${focusX * 100}% ${focusY * 100}%`,
          }}
        />
      </div>
    </div>
  );
};
