import { useEffect, useId, useRef, useState } from "react";

const MAX_GLINT_OFFSET = 1; // viewBox units -- keeps the glint inside the eye patch
const INK = "#3a2a24"; // near-black brown, panda-patch/outline color

// A small panda-faced helper for empty states -- shows a one-line tip in a
// speech bubble on hover instead of a plain "no documents yet" sentence.
// Also used at a smaller size in the nav bar to explain the app itself.
// The eye-patch highlights track the cursor anywhere on the page, and the
// eyes blink on their own -- both run independently of each other.
export default function Mascot({ tip, size = 60 }: { tip: string; size?: number }) {
  // Two Mascots can be on screen at once (nav + an empty state), so the
  // gradient needs a per-instance id -- a hardcoded id would duplicate
  // across SVGs and resolve inconsistently across browsers.
  const gradientId = `mascot-gradient-${useId()}`;
  const clipId = `mascot-face-clip-${useId()}`;
  const wrapRef = useRef<HTMLDivElement>(null);
  const [glint, setGlint] = useState({ x: 0, y: 0 });

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      const el = wrapRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      const dist = Math.hypot(dx, dy) || 1;
      // Direction only, scaled to a small fixed radius -- not real
      // distance -- so the glint stays inside the eye patch regardless of
      // how far away the cursor actually is.
      setGlint({ x: (dx / dist) * MAX_GLINT_OFFSET, y: (dy / dist) * MAX_GLINT_OFFSET });
    }
    window.addEventListener("mousemove", onMouseMove);
    return () => window.removeEventListener("mousemove", onMouseMove);
  }, []);

  return (
    <div className="mascot-wrap" ref={wrapRef}>
      <svg className="mascot-face" width={size} height={size * (52 / 64)} viewBox="0 0 64 52" fill="none" aria-hidden="true">
        {/* ears, drawn first so the face overlaps their lower half. Kept
            clear of the viewBox edge so they don't get clipped. */}
        <circle cx="13" cy="9.5" r="8.5" fill={INK} />
        <circle cx="51" cy="9.5" r="8.5" fill={INK} />
        {/* face: a plump dumpling body -- rounded sides and a wide belly,
            with a smooth (not pointed) rounded top. */}
        <path
          d="M8,28 C8,14 18,6 32,6 C46,6 56,14 56,28 C56,44 44,47 32,47 C20,47 8,44 8,28 Z"
          fill={`url(#${gradientId})`}
          stroke={INK}
          strokeWidth="2.25"
          strokeLinejoin="round"
        />
        {/* blush -- clipped to the face oval so the part that would spill
            past the outline is simply cut off, not floating outside it. */}
        <g clipPath={`url(#${clipId})`}>
          <circle cx="10" cy="32" r="5.5" fill="#ff9d8a" opacity="0.75" />
          <circle cx="54" cy="32" r="5.5" fill="#ff9d8a" opacity="0.75" />
        </g>
        {/* panda eye patches; the patch blinks, the glint tracks the cursor */}
        <g className="mascot-eyes">
          <ellipse cx="23" cy="25" rx="4" ry="5" fill={INK} />
          <ellipse cx="41" cy="25" rx="4" ry="5" fill={INK} />
          <circle cx={24 + glint.x} cy={23 + glint.y} r="1.1" fill="#ffffff" />
          <circle cx={42 + glint.x} cy={23 + glint.y} r="1.1" fill="#ffffff" />
        </g>
        {/* small "w" / cat-style mouth */}
        <path
          d="M28 35c1.2 2 2.8 2 4 0 1.2 2 2.8 2 4 0"
          stroke={INK}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <defs>
          <linearGradient id={gradientId} x1="8" y1="8" x2="56" y2="44" gradientUnits="userSpaceOnUse">
            <stop stopColor="#fff3ec" />
            <stop offset="1" stopColor="#ffd9c2" />
          </linearGradient>
          <clipPath id={clipId}>
            <path d="M8,28 C8,14 18,6 32,6 C46,6 56,14 56,28 C56,44 44,47 32,47 C20,47 8,44 8,28 Z" />
          </clipPath>
        </defs>
      </svg>
      <div className="mascot-tip" role="tooltip">
        {tip}
      </div>
    </div>
  );
}
