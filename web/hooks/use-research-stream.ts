"use client"

import * as React from "react"

import { searchURL } from "@/lib/api"
import { initialRun, runReducer } from "@/lib/run-state"
import type { StreamEvent } from "@/lib/types"

/** Starts a search on the backend and folds its Server-Sent Events into run state.
 * Unmounting closes the stream, which makes the server cancel the agents. */
export function useResearchStream(query: string, n: number) {
  const [state, dispatch] = React.useReducer(runReducer, query, initialRun)

  React.useEffect(() => {
    let es: EventSource | null = null
    let finished = false
    // Deferred so React's dev-mode double mount doesn't start (and pay for) two runs.
    const timer = setTimeout(() => {
      es = new EventSource(searchURL(query, n))
      es.onmessage = (msg) => {
        const ev = JSON.parse(msg.data) as StreamEvent
        if (ev.type === "done" || ev.type === "error") {
          finished = true
          es?.close()
        }
        dispatch(ev)
      }
      es.onerror = () => {
        if (finished) return
        es?.close()
        dispatch({ type: "disconnected" })
      }
    }, 0)
    return () => {
      clearTimeout(timer)
      es?.close()
    }
  }, [query, n])

  return state
}
