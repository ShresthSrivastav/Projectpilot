import { JetBrains_Mono, Inter } from "next/font/google"

export const fontChrome = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-chrome",
  display: "swap",
  preload: true,
})

export const fontVoice = Inter({
  subsets: ["latin"],
  variable: "--font-voice",
  display: "swap",
  preload: true,
})
