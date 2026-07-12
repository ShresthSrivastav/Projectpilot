import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { SkipToContent } from "../skip-to-content"

describe("SkipToContent", () => {
  it("renders the skip link with correct text", () => {
    render(<SkipToContent />)
    expect(screen.getByText("Skip to main content")).toBeInTheDocument()
  })

  it("links to #main-content", () => {
    render(<SkipToContent />)
    expect(screen.getByText("Skip to main content")).toHaveAttribute(
      "href",
      "#main-content"
    )
  })

  it("is initially hidden with sr-only class", () => {
    render(<SkipToContent />)
    const link = screen.getByText("Skip to main content")
    expect(link.className).toContain("sr-only")
  })

  it("is focusable", () => {
    render(<SkipToContent />)
    const link = screen.getByText("Skip to main content")
    link.focus()
    expect(document.activeElement).toBe(link)
  })
})
