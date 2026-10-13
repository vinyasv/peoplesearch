import Link from "next/link"

import { SiteHeader } from "@/components/site-header"
import { Button } from "@/components/ui/button"

export function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader>
        <Button variant="ghost" size="sm" render={<Link href="/" />} nativeButton={false}>
          New search
        </Button>
      </SiteHeader>
      <main className="mx-auto w-full max-w-6xl px-4 pt-10 pb-24 sm:px-8 sm:pt-14">
        {children}
      </main>
    </>
  )
}
