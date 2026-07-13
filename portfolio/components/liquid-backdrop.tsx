export function LiquidBackdrop() {
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none" aria-hidden="true">
      <div
        className="blob-1 absolute -top-48 -left-48 w-[600px] h-[600px] rounded-full opacity-[0.08] dark:opacity-[0.06]"
        style={{
          background:
            "radial-gradient(circle, #2DD4BF 0%, #06B6D4 40%, transparent 70%)",
          filter: "blur(80px)",
        }}
      />
      <div
        className="blob-2 absolute top-1/3 -right-64 w-[500px] h-[500px] rounded-full opacity-[0.06] dark:opacity-[0.05]"
        style={{
          background:
            "radial-gradient(circle, #818CF8 0%, #6366F1 40%, transparent 70%)",
          filter: "blur(80px)",
        }}
      />
      <div
        className="blob-3 absolute -bottom-48 left-1/4 w-[550px] h-[550px] rounded-full opacity-[0.06] dark:opacity-[0.04]"
        style={{
          background:
            "radial-gradient(circle, #2DD4BF 0%, #14B8A6 40%, transparent 70%)",
          filter: "blur(80px)",
        }}
      />
    </div>
  )
}
