import { notFound } from 'next/navigation'
import { PlanGate } from '@/components/PlanGate'
import GlobalIndexDetail from './GlobalIndexDetail'

const INTERNAL_API = process.env.INTERNAL_API_URL || 'http://localhost:8000'

export default async function GlobalIndexDetailPage({
  params,
}: {
  params: Promise<{ code: string }>
}) {
  const { code } = await params
  const upperCode = code.toUpperCase()

  let detail
  try {
    const res = await fetch(
      `${INTERNAL_API}/api/v1/global-markets/${upperCode}?days=365`,
      { cache: 'no-store' }
    )
    if (!res.ok) notFound()
    detail = await res.json()
  } catch {
    notFound()
  }

  return (
    <PlanGate required="premium" feature="Global Markets">
      <GlobalIndexDetail initialData={detail} code={upperCode} />
    </PlanGate>
  )
}
