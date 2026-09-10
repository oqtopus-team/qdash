import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Background } from "../components/Background";
import { font, theme } from "../theme";

export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const logo = spring({ frame, fps, config: { damping: 14, stiffness: 90 } });
  const title = spring({
    frame: frame - 12,
    fps,
    config: { damping: 200, stiffness: 110 },
  });
  const tagline = spring({
    frame: frame - 30,
    fps,
    config: { damping: 200, stiffness: 110 },
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 14, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill style={{ opacity: fadeOut }}>
      <Background />
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          fontFamily: font,
          color: theme.ink,
        }}
      >
        <Img
          src={staticFile("oqtopus-symbol.png")}
          style={{
            width: 260,
            height: 260,
            transform: `scale(${logo}) rotate(${interpolate(logo, [0, 1], [-18, 0])}deg)`,
            filter: "drop-shadow(0 24px 40px rgba(31,26,61,0.25))",
          }}
        />
        <div
          style={{
            marginTop: 26,
            fontSize: 150,
            fontWeight: 900,
            letterSpacing: -5,
            lineHeight: 1,
            background: `linear-gradient(90deg, ${theme.violet}, ${theme.pink})`,
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
            color: "transparent",
            opacity: title,
            transform: `translateY(${interpolate(title, [0, 1], [40, 0])}px)`,
          }}
        >
          QDash
        </div>
        <div
          style={{
            marginTop: 18,
            fontSize: 40,
            fontWeight: 500,
            color: theme.inkMuted,
            opacity: tagline,
            transform: `translateY(${interpolate(tagline, [0, 1], [24, 0])}px)`,
          }}
        >
          Qubit Calibration Platform
        </div>
        <div
          style={{
            marginTop: 14,
            fontSize: 26,
            color: theme.inkMuted,
            opacity: tagline * 0.85,
          }}
        >
          Manage and monitor qubit calibration workflows with ease
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
