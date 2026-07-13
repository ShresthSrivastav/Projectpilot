"use client"

import { SoundToggle } from "./sound-toggle"
import { ThemeToggle } from "./theme-toggle"

const navLinks = [
  { label: "Work", href: "#work" },
  { label: "Contact", href: "#contact" },
]

export function Nav() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 px-4 sm:px-8 py-4">
      <nav className="max-w-5xl mx-auto flex items-center justify-between">
        <a
          href="#"
          className="chrome text-sm tracking-[0.15em] text-[var(--color-text)] no-underline hover:text-[var(--color-accent)] transition-colors duration-150"
        >
          SHRESTH
        </a>

        <div className="flex items-center gap-6">
          <div className="glass-pill flex items-center gap-5 px-5 py-1.5">
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="chrome text-[13px] text-[var(--color-muted)] no-underline hover:text-[var(--color-accent)] transition-colors duration-150"
              >
                {link.label}
              </a>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <ThemeToggle />
            <SoundToggle />
          </div>
        </div>
      </nav>
    </header>
  )
}
