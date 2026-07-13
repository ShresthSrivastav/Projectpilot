"use client"

import { motion } from "framer-motion"
import { ScrollReveal } from "./scroll-reveal"

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.2 },
  },
}

const item = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.25, 0.1, 0.25, 1] as const } },
}

export function Hero() {
  return (
    <section className="min-h-screen flex flex-col justify-center px-4 sm:px-8 pt-24 pb-16">
      <div className="max-w-5xl mx-auto w-full">
        <motion.div variants={container} initial="hidden" animate="show" className="space-y-10">
          <motion.div variants={item} className="space-y-2">
            <h1 className="text-[clamp(2.5rem,6vw,5rem)] leading-[1.05] font-light tracking-tight">
              Systems{" "}
              <span className="font-semibold text-[var(--color-accent)]">&</span>{" "}
              Design
            </h1>
            <h1 className="text-[clamp(2.5rem,6vw,5rem)] leading-[1.05] font-light tracking-tight">
              Engineer & Architect
            </h1>
          </motion.div>

          <motion.p
            variants={item}
            className="text-lg sm:text-xl leading-relaxed max-w-[60ch] text-[var(--color-muted)]"
          >
            I design and build systems that augment how people think, create, and ship
            software. Currently focused on autonomous AI workflows, developer tooling, and
            infrastructure that stays out of the way.
          </motion.p>

          <motion.div variants={item} className="flex items-center gap-4">
            <span className="chrome text-xs text-[var(--color-muted)]">
              AVAILABLE FOR COLLABORATION
            </span>
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
          </motion.div>
        </motion.div>
      </div>
    </section>
  )
}
