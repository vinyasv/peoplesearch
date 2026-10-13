import type { Metadata } from "next"
import { Geist_Mono, Newsreader, Schibsted_Grotesk } from "next/font/google"

import "./globals.css"
import { TooltipProvider } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

export const metadata: Metadata = {
  title: "People research",
  description: "Find people who match every requirement, checked by research agents with citations.",
}

const sans = Schibsted_Grotesk({ subsets: ["latin"], variable: "--font-sans" })

// Reserved for words people wrote: the search brief and quotes from sources.
const serif = Newsreader({
  subsets: ["latin"],
  variable: "--font-serif",
  style: ["normal", "italic"],
  axes: ["opsz"],
})

const fontMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
})

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={cn("antialiased", fontMono.variable, "font-sans", sans.variable, serif.variable)}
    >
      <body className="min-h-svh bg-background">
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  )
}
