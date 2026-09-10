import { Composition } from "remotion";
import { QDashDemo, DURATION_IN_FRAMES, FPS } from "./QDashDemo";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="QDashDemo"
      component={QDashDemo}
      durationInFrames={DURATION_IN_FRAMES}
      fps={FPS}
      width={1920}
      height={1080}
    />
  );
};
