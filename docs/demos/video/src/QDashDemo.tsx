import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { Intro } from "./scenes/Intro";
import { FeatureScene, type Feature } from "./scenes/FeatureScene";
import { Outro } from "./scenes/Outro";
import { theme } from "./theme";

export const FPS = 30;

// Scene timing (seconds). Total = 30s.
const INTRO = 4;
const FEATURE = 4.4;
const OUTRO = 4;

const FEATURES: Feature[] = [
  {
    step: "Overview",
    title: "Chip health at a glance",
    bullets: [
      "Every metric on a 64-qubit heatmap",
      "Coverage and CDF per parameter",
      "Latest, best, or average per cooldown",
    ],
    screenshot: "screens/dashboard-t1-blur.png",
    url: "qdash.example/dashboard",
    accent: theme.violet,
    focusX: 0.35,
    focusY: 0.55,
  },
  {
    step: "Inspect",
    title: "Every qubit, every result",
    bullets: [
      "Chip topology with MUX grouping",
      "Fit previews for each calibration task",
      "Qubit, coupling, and MUX views",
    ],
    screenshot: "screens/chip-grid.png",
    url: "qdash.example/chip",
    accent: theme.pink,
    focusX: 0.55,
    focusY: 0.6,
  },
  {
    step: "Run",
    title: "Run calibrations",
    bullets: [
      "Reusable workflows shared per project",
      "Bring-up, coarse, fine-tune, and 2Q pipelines",
      "Schedule with cron or run on demand",
    ],
    screenshot: "screens/workflow.png",
    url: "qdash.example/workflow",
    accent: theme.violet,
    focusX: 0.4,
    focusY: 0.4,
  },
  {
    step: "Monitor",
    title: "Follow live executions",
    bullets: [
      "Task graph updates while calibration runs",
      "Click a node to see its fit and parameters",
      "Failures surface with stack traces",
    ],
    screenshot: "screens/execution-flow-crop.png",
    url: "qdash.example/execution",
    accent: theme.emerald,
    focusX: 0.8,
    focusY: 0.75,
  },
  {
    step: "Analyze",
    title: "Track trends over time",
    bullets: [
      "Time series, histogram, CDF, correlation",
      "Compare parameters across cooldowns",
      "Export CSV or ask the AI assistant",
    ],
    screenshot: "screens/analysis-blur.png",
    url: "qdash.example/analysis",
    accent: theme.pink,
    focusX: 0.5,
    focusY: 0.45,
  },
];

const f = (s: number) => Math.round(s * FPS);

export const DURATION_IN_FRAMES = f(INTRO + FEATURE * FEATURES.length + OUTRO);

export const QDashDemo: React.FC = () => {
  let cursor = 0;
  const seq = (dur: number) => {
    const from = cursor;
    cursor += f(dur);
    return { from, durationInFrames: f(dur) };
  };

  return (
    <AbsoluteFill style={{ background: theme.base }}>
      {/* Original synthesized BGM (see scripts/make_bgm.py); fades are baked in. */}
      <Audio src={staticFile("bgm.m4a")} volume={0.85} />
      <Sequence {...seq(INTRO)}>
        <Intro />
      </Sequence>
      {FEATURES.map((feature) => (
        <Sequence key={feature.step} {...seq(FEATURE)}>
          <FeatureScene {...feature} />
        </Sequence>
      ))}
      <Sequence {...seq(OUTRO)}>
        <Outro />
      </Sequence>
    </AbsoluteFill>
  );
};
