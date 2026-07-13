import type { Metadata } from "next"
import { fontChrome, fontVoice } from "./fonts"
import { Providers } from "./providers"
import { Nav } from "@/components/nav"
import { Footer } from "@/components/footer"
import { HUD } from "@/components/hud"
import { LiquidBackdrop } from "@/components/liquid-backdrop"
import "./globals.css"

export const metadata: Metadata = {
  title: "Shresth Srivastav — Systems & Design Engineer",
  description:
    "Systems & design engineer building autonomous AI workflows, developer tooling, and infrastructure.",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${fontChrome.variable} ${fontVoice.variable}`}>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const theme = localStorage.getItem('theme');
                if (theme === 'light') document.documentElement.classList.remove('dark');
                else document.documentElement.classList.add('dark');
              } catch(e) {}
            `,
          }}
        />
      </head>
      <body className="antialiased">
        <Providers>
          <LiquidBackdrop />
          <Nav />
          <main>{children}</main>
          <Footer />
          <HUD />
        </Providers>
      </body>
    </html>
  )
}
