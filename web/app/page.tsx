import Link from "next/link"

import { RecentRuns } from "@/components/recent-runs"
import { SearchForm } from "@/components/search-form"
import { SiteHeader } from "@/components/site-header"
import { EXAMPLES, searchHref } from "@/lib/search"

export default function Page() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-6xl flex-col gap-20 px-4 pt-16 pb-24 sm:px-8 sm:pt-24">
        <div className="max-w-3xl">
          <SearchForm />
        </div>

        <div className="grid gap-14 border-t pt-10 lg:grid-cols-2 lg:gap-20">
          <section className="flex flex-col gap-5">
            <h2 className="text-sm font-medium">Examples</h2>
            <ul className="flex flex-col gap-5">
              {EXAMPLES.map((ex) => (
                <li key={ex}>
                  <Link
                    href={searchHref(ex, 10)}
                    className="font-serif text-[17px] leading-snug text-muted-foreground decoration-muted-foreground/50 underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:underline"
                  >
                    {ex}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
          <section className="flex flex-col gap-5">
            <h2 className="text-sm font-medium">Past searches</h2>
            <RecentRuns />
          </section>
        </div>
      </main>
    </>
  )
}
