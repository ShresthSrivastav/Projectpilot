"use client"

import { motion } from "framer-motion"
import { ScrollReveal } from "./scroll-reveal"

const lineVariants = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, delay: i * 0.12, ease: [0.25, 0.1, 0.25, 1] as const },
  }),
}

const lines = ["Let's Create", "Something", "Extraordinary"]

export function CTASection() {
  return (
    <section className="px-4 sm:px-8 py-32">
      <div className="max-w-5xl mx-auto w-full">
        <ScrollReveal>
          <div className="space-y-0">
            {lines.map((line, i) => (
              <motion.p
                key={line}
                custom={i}
                variants={lineVariants}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true }}
                className={`text-[clamp(2.5rem,6vw,5rem)] leading-[1.05] font-light tracking-tight ${
                  i === 2 ? "text-[var(--color-accent)] font-semibold" : ""
                }`}
              >
                {line}
              </motion.p>
            ))}
            <div className="mt-10">
              <a
                href="mailto:shresth@example.com"
                className="inline-block chrome text-sm text-[var(--color-muted)] no-underline hover:text-[var(--color-accent)] transition-colors duration-150 border border-[var(--color-border)] dark:border-[var(--color-border)] rounded-[999px] px-6 py-3"
              >
                shresth@example.com →
              </a>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  )
}
