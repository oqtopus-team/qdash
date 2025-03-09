"use client";

interface TaskFigureProps {
  path: string | string[];
  qid: string;
  className?: string;
}

export function TaskFigure({ path, qid, className = "" }: TaskFigureProps) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  if (Array.isArray(path)) {
    return (
      <>
        {path.map((p, i) => (
          <img
            key={i}
            src={`${apiUrl}/api/executions/figure?path=${encodeURIComponent(
              p
            )}`}
            alt={`Result for QID ${qid}`}
            className={className}
          />
        ))}
      </>
    );
  }

  return (
    <img
      src={`${apiUrl}/api/executions/figure?path=${encodeURIComponent(path)}`}
      alt={`Result for QID ${qid}`}
      className={className}
    />
  );
}
