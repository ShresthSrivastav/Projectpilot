"use client"

import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ScrollReveal } from "./scroll-reveal"
import { GlassPanel } from "./glass-panel"
import { projects } from "@/lib/projects"

export function ProjectList() {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })

  return (
    <section id="work" className="px-4 sm:px-8 py-24">
      <div className="max-w-5xl mx-auto w-full">
        <ScrollReveal>
          <h2 className="chrome text-xs text-[var(--color-muted)] mb-12">Selected Work</h2>
        </ScrollReveal>

        <div className="space-y-0">
          {projects.map((project, i) => (
            <ScrollReveal key={project.title} delay={i * 0.08}>
              <a
                href={project.url || "#"}
                target={project.url ? "_blank" : undefined}
                rel={project.url ? "noopener noreferrer" : undefined}
                className="group relative block py-6 border-t border-[var(--color-border)] dark:border-[var(--color-border)] no-underline cursor-pointer"
                onMouseEnter={(e) => {
                  setHoveredIndex(i)
                  setMousePos({ x: e.clientX, y: e.clientY })
                }}
                onMouseMove={(e) => setMousePos({ x: e.clientX, y: e.clientY })}
                onMouseLeave={() => setHoveredIndex(null)}
              >
                <div className="flex items-baseline justify-between gap-4">
                  <div className="flex items-baseline gap-4 min-w-0">
                    <span className="text-lg sm:text-xl font-light text-[var(--color-text)] dark:text-[var(--color-text)] group-hover:text-[var(--color-accent)] transition-colors duration-150">
                      {project.title}
                    </span>
                    <span className="chrome text-xs text-[var(--color-muted)] shrink-0">
                      {project.year}
                    </span>
                  </div>
                  <span className="chrome text-xs text-[var(--color-muted)] shrink-0 group-hover:text-[var(--color-accent)] transition-colors duration-150">
                    {project.url ? "tools →" : ""}
                  </span>
                </div>

                <AnimatePresence>
                  {hoveredIndex === i && (
                    <motion.div
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 4 }}
                      transition={{ duration: 0.15 }}
                      className="pt-2"
                    >
                      <p className="text-sm leading-relaxed text-[var(--color-muted)] max-w-[70ch]">
                        {project.description}
                      </p>
                      {project.tags && (
                        <div className="flex gap-2 mt-2">
                          {project.tags.map((tag) => (
                            <span
                              key={tag}
                              className="chrome text-[11px] text-[var(--color-accent)]"
                            >
                              [{tag}]
                            </span>
                          ))}
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </a>
            </ScrollReveal>
          ))}
        </div>

        <div className="border-t border-[var(--color-border)] dark:border-[var(--color-border)] pt-2">
          <span className="chrome text-xs text-[var(--color-muted)]">
            + 3 more projects not yet listed
          </span>
        </div>
      </div>
    </section>
  )
}
