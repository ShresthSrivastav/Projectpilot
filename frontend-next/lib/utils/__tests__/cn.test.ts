import { describe, it, expect } from "vitest"
import { cn } from "../cn"

describe("cn", () => {
  it("merges multiple class names", () => {
    expect(cn("px-4", "py-2")).toBe("px-4 py-2")
  })

  it("filters out falsy values", () => {
    expect(cn("base", false && "hidden", undefined, null, "visible")).toBe("base visible")
  })

  it("merges conflicting Tailwind classes (last wins)", () => {
    expect(cn("px-4", "px-6")).toBe("px-6")
  })

  it("handles conditional classes from arrays", () => {
    expect(cn(["a", "b"], "c")).toBe("a b c")
  })

  it("returns empty string for no inputs", () => {
    expect(cn()).toBe("")
  })
})
