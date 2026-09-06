import { useEffect, useRef, useState } from "react";
import { getDevToken, setDevToken } from "../api/client";

// A native <select>'s open dropdown list is rendered by the OS/browser and
// can't be themed with CSS -- it looked jarringly plain against the rest
// of the glass UI. This is a fully custom-styled equivalent (button +
// positioned menu) so the open state matches everything else.
const USERS = [
  { token: "dev-key-alice", label: "alice" },
  { token: "dev-key-bob", label: "bob" },
];

export default function UserSwitcher() {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState(getDevToken());
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  function choose(token: string) {
    setCurrent(token);
    setDevToken(token);
    setOpen(false);
    window.location.reload();
  }

  const currentLabel = USERS.find((u) => u.token === current)?.label ?? "alice";

  return (
    <div className="user-switcher-wrap" ref={rootRef}>
      <button
        type="button"
        className="user-switcher"
        onClick={() => setOpen((v) => !v)}
        title="Dev-grade auth: swaps the demo user (see backend/app/core/security.py)"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {currentLabel}
        <svg width="10" height="6" viewBox="0 0 10 6" fill="none" aria-hidden="true">
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <ul className="user-switcher-menu" role="listbox">
          {USERS.map((u) => (
            <li
              key={u.token}
              role="option"
              aria-selected={u.token === current}
              className={u.token === current ? "selected" : ""}
              onClick={() => choose(u.token)}
            >
              {u.label}
              {u.token === current && (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    d="M5 13l4 4L19 7"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
