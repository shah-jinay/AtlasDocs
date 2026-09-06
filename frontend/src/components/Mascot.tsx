import { useEffect, useId, useRef, useState } from "react";

const MAX_GLINT_OFFSET = 1; // viewBox units -- keeps the glint inside the eye patch
const INK = "#3a2a24"; // near-black brown, panda-patch/outline color

// A small panda-faced helper for empty states -- shows a one-line tip in a
// speech bubble on hover instead of a plain "no documents yet" sentence.
// Also used at a smaller size in the nav bar to explain the app itself.
// The eye-patch highlights track the cursor anywhere on the page, and the
// eyes blink on their own -- both run independently of each other.
export default function Mascot({ tip, size = 52 }: { tip: string; size?: number }) {
  // Two Mascots can be on screen at once (nav + an empty state), so the
  // gradient needs a per-instance id -- a hardcoded id would duplicate
  // across SVGs and resolve inconsistently across browsers.
  const gradientId = `mascot-gradient-${useId()}`;
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
      <svg className="mascot-face" width={size} height={size} viewBox="0 0 56 56" fill="none" aria-hidden="true">
        {/* ears, drawn first so the face circle overlaps their inner edge */}
        <circle cx="14" cy="13" r="7.5" fill={INK} />
        <circle cx="42" cy="13" r="7.5" fill={INK} />
        {/* face: a domed top (rounded like a circle) but a flat-ish
            bottom with just softly rounded corners, rather than a full
            circle -- reads as "sitting" on a surface. */}
        <path
          d="M5,33 A23,23 0 0 1 28,10 A23,23 0 0 1 51,33 L51,49 A5,5 0 0 1 46,54 L10,54 A5,5 0 0 1 5,49 Z"
          fill={`url(#${gradientId})`}
          stroke={INK}
          strokeWidth="2.25"
          strokeLinejoin="round"
        />
        {/* blush, peeking out beside the eye patches */}
        <circle cx="12.5" cy="38" r="3.5" fill="#ff9d8a" opacity="0.6" />
        <circle cx="43.5" cy="38" r="3.5" fill="#ff9d8a" opacity="0.6" />
        {/* panda eye patches; the patch blinks, the glint tracks the cursor */}
        <g className="mascot-eyes">
          <ellipse cx="18.5" cy="28" rx="4.5" ry="5.5" fill={INK} />
          <ellipse cx="37.5" cy="28" rx="4.5" ry="5.5" fill={INK} />
          <circle cx={19.5 + glint.x} cy={26 + glint.y} r="1.1" fill="#ffffff" />
          <circle cx={38.5 + glint.x} cy={26 + glint.y} r="1.1" fill="#ffffff" />
        </g>
        {/* nose */}
        <ellipse cx="28" cy="38.5" rx="2.2" ry="1.6" fill={INK} />
        {/* small "w" / cat-style mouth */}
        <path
          d="M22 44c1.2 2 2.8 2 4 0 1.2 2 2.8 2 4 0 1.2 2 2.8 2 4 0"
          stroke={INK}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <defs>
          <linearGradient id={gradientId} x1="7" y1="10" x2="49" y2="52" gradientUnits="userSpaceOnUse">
            <stop stopColor="#fff3ec" />
            <stop offset="1" stopColor="#ffd9c2" />
          </linearGradient>
        </defs>
      </svg>
      <div className="mascot-tip" role="tooltip">
        {tip}
      </div>
    </div>
  );
}
