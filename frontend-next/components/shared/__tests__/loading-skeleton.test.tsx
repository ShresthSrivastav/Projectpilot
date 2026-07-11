import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import { SkeletonCard, SkeletonTable, SkeletonChart } from "../loading-skeleton"

describe("SkeletonCard", () => {
  it("renders a single card by default", () => {
    const { container } = render(<SkeletonCard />)
    expect(container.querySelectorAll(".rounded-lg").length).toBe(1)
  })

  it("renders multiple cards with count prop", () => {
    const { container } = render(<SkeletonCard count={3} />)
    expect(container.querySelectorAll(".rounded-lg").length).toBe(3)
  })

  it("renders shimmer elements inside each card", () => {
    const { container } = render(<SkeletonCard count={2} />)
    expect(container.querySelectorAll(".shimmer-bg").length).toBe(6)
  })

  it("applies custom className", () => {
    const { container } = render(<SkeletonCard className="custom-class" />)
    expect(container.querySelector(".custom-class")).toBeInTheDocument()
  })
})

describe("SkeletonTable", () => {
  it("renders a header row plus default 5 data rows", () => {
    const { container } = render(<SkeletonTable />)
    expect(container.querySelectorAll(".shimmer-bg").length).toBe(24)
  })

  it("renders custom number of rows", () => {
    const { container } = render(<SkeletonTable rows={3} />)
    expect(container.querySelectorAll(".shimmer-bg").length).toBe(16)
  })
})

describe("SkeletonChart", () => {
  it("renders the chart container", () => {
    const { container } = render(<SkeletonChart />)
    expect(container.querySelector(".rounded-lg")).toBeInTheDocument()
  })

  it("renders 8 bar placeholders", () => {
    const { container } = render(<SkeletonChart />)
    expect(container.querySelectorAll(".flex-1").length).toBe(8)
  })
})
