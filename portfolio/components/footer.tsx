import { ScrollReveal } from "./scroll-reveal"

const socialLinks = [
  { label: "GitHub", href: "https://github.com/ShresthSrivastav" },
  { label: "LinkedIn", href: "#" },
  { label: "Twitter", href: "#" },
]

export function Footer() {
  return (
    <footer id="contact" className="px-4 sm:px-8 py-12 border-t border-[var(--color-border)] dark:border-[var(--color-border)]">
      <div className="max-w-5xl mx-auto w-full flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <ScrollReveal>
          <p className="chrome text-xs text-[var(--color-muted)]">
            © {new Date().getFullYear()} Shresth Srivastav
          </p>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <div className="flex items-center gap-6">
            {socialLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                target="_blank"
                rel="noopener noreferrer"
                className="chrome text-xs text-[var(--color-muted)] no-underline hover:text-[var(--color-accent)] transition-colors duration-150"
              >
                {link.label}
              </a>
            ))}
          </div>
        </ScrollReveal>

        <ScrollReveal delay={0.15}>
          <a
            href="mailto:shresth@example.com"
            className="chrome text-xs text-[var(--color-muted)] no-underline hover:text-[var(--color-accent)] transition-colors duration-150"
          >
            shresth@example.com
          </a>
        </ScrollReveal>
      </div>
    </footer>
  )
}
