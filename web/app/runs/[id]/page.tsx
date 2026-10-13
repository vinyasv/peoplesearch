import { SavedRun } from "./saved-run"

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return <SavedRun id={decodeURIComponent(id)} />
}
