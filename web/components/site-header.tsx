import Link from "next/link"

export function SiteHeader({ children }: { children?: React.ReactNode }) {
  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-8">
        <Link
          href="/"
          className="text-[15px] font-semibold tracking-tight outline-none focus-visible:underline"
        >
          People research
        </Link>
        {children}
      </div>
    </header>
  )
}
