"use client";

import React, { useEffect, useRef, useState } from "react";


export function ScoreRing({ score }: { score: number }) {
  const [isVisible, setIsVisible] = useState(false);
  const ringRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ringRef.current;
    if (!node) {
      return;
    }

    if (typeof IntersectionObserver === "undefined") {
      const frame = requestAnimationFrame(() => setIsVisible(true));
      return () => cancelAnimationFrame(frame);
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setIsVisible(false);
          requestAnimationFrame(() => setIsVisible(true));
          observer.disconnect();
        }
      },
      { threshold: 0.45 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ringRef}
      className={isVisible ? "score-ring score-ring-tech score-ring-orbit is-visible" : "score-ring score-ring-tech score-ring-orbit"}
      style={{ "--target-score": `${score}%` } as React.CSSProperties}
      data-target-score={score}
      aria-label={`综合得分 ${score}%`}
    >
      <span>{score}</span>
      <small>{"%"}</small>
    </div>
  );
}
