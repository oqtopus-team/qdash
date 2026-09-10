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

export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fadeIn = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });
  const pop = spring({ frame, fps, config: { damping: 200, stiffness: 110 } });
  const links = spring({
    frame: frame - 18,
    fps,
    config: { damping: 200, stiffness: 110 },
  });

  const Chip: React.FC<{ label: string; delay: number }> = ({ label, delay }) => {
    const s = spring({
      frame: frame - 24 - delay,
      fps,
      config: { damping: 200, stiffness: 140 },
    });
    return (
      <div
        style={{
          padding: "12px 24px",
          borderRadius: 999,
          background: "rgba(255,255,255,0.10)",
          border: "1px solid rgba(255,255,255,0.25)",
          color: theme.white,
          fontSize: 24,
          fontWeight: 600,
          opacity: s,
          transform: `translateY(${interpolate(s, [0, 1], [14, 0])}px)`,
        }}
      >
        {label}
      </div>
    );
  };

  return (
    <AbsoluteFill style={{ opacity: fadeIn }}>
      <Background dark />
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          fontFamily: font,
          color: theme.white,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 34,
            opacity: pop,
            transform: `scale(${interpolate(pop, [0, 1], [0.9, 1])})`,
          }}
        >
          <Img
            src={staticFile("oqtopus-symbol.png")}
            style={{ width: 150, height: 150 }}
          />
          <div
            style={{
              fontSize: 130,
              fontWeight: 900,
              letterSpacing: -4,
              background: `linear-gradient(90deg, #a5b4fc, ${theme.pink})`,
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
              color: "transparent",
            }}
          >
            QDash
          </div>
        </div>
        <div
          style={{
            marginTop: 30,
            fontSize: 40,
            fontWeight: 600,
            opacity: links,
            transform: `translateY(${interpolate(links, [0, 1], [20, 0])}px)`,
          }}
        >
          oqtopus-team.github.io/qdash
        </div>
        <div
          style={{
            marginTop: 12,
            fontSize: 28,
            color: "rgba(255,255,255,0.75)",
            opacity: links,
          }}
        >
          github.com/oqtopus-team/qdash
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 44 }}>
          <Chip label="Open Source · Apache 2.0" delay={0} />
          <Chip label="FastAPI · Next.js · Prefect" delay={6} />
          <Chip label="Built by OQTOPUS" delay={12} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
