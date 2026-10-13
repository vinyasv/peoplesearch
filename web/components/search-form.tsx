"use client"

import * as React from "react"
import { useRouter } from "next/navigation"

import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { searchHref } from "@/lib/search"

const SIZES = [5, 10, 15, 20].map((n) => ({ label: String(n), value: String(n) }))

export function SearchForm() {
  const router = useRouter()
  const [query, setQuery] = React.useState("")
  const [n, setN] = React.useState("10")
  const ready = query.trim().length >= 3

  function submit(e?: React.FormEvent) {
    e?.preventDefault()
    if (ready) router.push(searchHref(query.trim(), n))
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <Field>
        <FieldLabel htmlFor="brief" className="text-base font-medium">
          Who are you looking for?
        </FieldLabel>
        <Textarea
          id="brief"
          autoFocus
          rows={3}
          maxLength={500}
          placeholder="Rust developers in San Francisco who maintain an open-source project with 1,000+ stars"
          className="field-sizing-content min-h-[3lh] resize-none rounded-none border-0 border-b-2 border-input bg-transparent px-0 py-2 font-serif text-2xl leading-snug shadow-none placeholder:text-muted-foreground/60 focus-visible:border-foreground focus-visible:ring-0 sm:text-[28px] md:text-[28px] dark:bg-transparent"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
        />
        <FieldDescription>
          Name the role, place and anything you can verify, like years of
          experience, a paper or a project. Each requirement is checked on its
          own.
        </FieldDescription>
      </Field>
      <div className="flex items-center justify-end gap-3">
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          Check
          <Select items={SIZES} value={n} onValueChange={(v) => v && setN(v)}>
            <SelectTrigger size="sm" aria-label="Number of people to check">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {SIZES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          people
        </span>
        <Button type="submit" disabled={!ready}>
          Search
        </Button>
      </div>
    </form>
  )
}
