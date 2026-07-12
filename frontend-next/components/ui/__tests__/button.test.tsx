import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { Button } from "../button"

describe("Button", () => {
  it("renders children text", () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole("button", { name: /click me/i })).toBeInTheDocument()
  })

  it("renders with default variant classes", () => {
    render(<Button>Default</Button>)
    expect(screen.getByRole("button").className).toContain("bg-primary")
  })

  it("renders with destructive variant", () => {
    render(<Button variant="destructive">Delete</Button>)
    expect(screen.getByRole("button").className).toContain("bg-error")
  })

  it("renders with outline variant", () => {
    render(<Button variant="outline">Outline</Button>)
    expect(screen.getByRole("button").className).toContain("border-border")
  })

  it("renders with secondary variant", () => {
    render(<Button variant="secondary">Secondary</Button>)
    expect(screen.getByRole("button").className).toContain("bg-muted")
  })

  it("renders with ghost variant", () => {
    render(<Button variant="ghost">Ghost</Button>)
    expect(screen.getByRole("button").className).toContain("hover:bg-card-hover")
  })

  it("renders with link variant", () => {
    render(<Button variant="link">Link</Button>)
    expect(screen.getByRole("button").className).toContain("hover:underline")
  })

  it("renders with accent variant", () => {
    render(<Button variant="accent">Accent</Button>)
    expect(screen.getByRole("button").className).toContain("bg-accent")
  })

  it("renders with different sizes", () => {
    const { rerender } = render(<Button size="sm">Small</Button>)
    expect(screen.getByRole("button").className).toContain("h-8")
    rerender(<Button size="lg">Large</Button>)
    expect(screen.getByRole("button").className).toContain("h-10")
    rerender(<Button size="xl">XL</Button>)
    expect(screen.getByRole("button").className).toContain("h-12")
    rerender(<Button size="icon">Icon</Button>)
    expect(screen.getByRole("button").className).toContain("h-9")
    rerender(<Button size="icon-sm">IconSm</Button>)
    expect(screen.getByRole("button").className).toContain("h-8")
  })

  it("renders as a child element when asChild is true", () => {
    render(
      <Button asChild>
        <a href="/test">Link Button</a>
      </Button>
    )
    expect(screen.getByRole("link", { name: /link button/i })).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("applies additional className", () => {
    render(<Button className="my-custom-class">Styled</Button>)
    expect(screen.getByRole("button").className).toContain("my-custom-class")
  })

  it("renders as a button element by default", () => {
    render(<Button>Native</Button>)
    expect(screen.getByRole("button").tagName).toBe("BUTTON")
  })
})
