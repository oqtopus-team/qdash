import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../components/Background";
import { BrowserFrame } from "../components/BrowserFrame";
import { Caption } from "../components/Caption";

export type Feature = {
  step: string;
  title: string;
  bullets: string[];
  screenshot: string;
  url: string;
  accent?: string;
  focusX?: number;
  focusY?: number;
};

const FRAME_WIDTH = 1380;

export const FeatureScene: React.FC<Feature> = ({
  step,
  title,
  bullets,
  screenshot,
  url,
  accent,
  focusX,
  focusY,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const enter = spring({
    frame: frame - 4,
    fps,
    config: { damping: 200, stiffness: 100 },
  });
  const fadeIn = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 12, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill style={{ opacity: Math.min(fadeIn, fadeOut) }}>
      <Background />
      <AbsoluteFill
        style={{
          flexDirection: "row",
          alignItems: "center",
          padding: "0 80px",
          gap: 60,
        }}
      >
        <Caption step={step} title={title} bullets={bullets} accent={accent} />
        <div
          style={{
            transform: `translateX(${interpolate(enter, [0, 1], [140, 0])}px) rotateY(${interpolate(enter, [0, 1], [-8, 0])}deg)`,
            opacity: enter,
            perspective: 1600,
            flexShrink: 0,
          }}
        >
          <BrowserFrame
            src={screenshot}
            url={url}
            width={FRAME_WIDTH}
            durationInFrames={durationInFrames}
            focusX={focusX}
            focusY={focusY}
          />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
