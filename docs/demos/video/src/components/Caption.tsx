import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { font, theme } from "../theme";

type Props = {
  step: string;
  title: string;
  bullets: string[];
  accent?: string;
};

/** Left-side feature card that slides in and reveals bullets one by one. */
export const Caption: React.FC<Props> = ({
  step,
  title,
  bullets,
  accent = theme.violet,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 120 } });
  const x = interpolate(enter, [0, 1], [-80, 0]);

  return (
    <div
      style={{
        fontFamily: font,
        color: theme.ink,
        transform: `translateX(${x}px)`,
        opacity: enter,
        width: 500,
        flexShrink: 0,
      }}
    >
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 10,
          padding: "6px 14px",
          borderRadius: 999,
          background: accent,
          color: theme.white,
          fontSize: 20,
          fontWeight: 700,
          letterSpacing: 1.5,
          textTransform: "uppercase",
        }}
      >
        {step}
      </div>
      <h2
        style={{
          fontSize: 64,
          lineHeight: 1.08,
          fontWeight: 800,
          margin: "22px 0 26px",
          letterSpacing: -1.5,
        }}
      >
        {title}
      </h2>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {bullets.map((b, i) => {
          const s = spring({
            frame: frame - 10 - i * 8,
            fps,
            config: { damping: 200, stiffness: 140 },
          });
          return (
            <li
              key={b}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 14,
                fontSize: 27,
                lineHeight: 1.35,
                color: theme.inkMuted,
                marginBottom: 14,
                opacity: s,
                transform: `translateY(${interpolate(s, [0, 1], [16, 0])}px)`,
              }}
            >
              <span
                style={{
                  marginTop: 12,
                  width: 12,
                  height: 12,
                  borderRadius: "50%",
                  background: accent,
                  flexShrink: 0,
                }}
              />
              {b}
            </li>
          );
        })}
      </ul>
    </div>
  );
};
