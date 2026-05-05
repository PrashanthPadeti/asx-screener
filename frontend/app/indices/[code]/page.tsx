import { notFound } from 'next/navigation'
import { PlanGate } from '@/components/PlanGate'
import IndexDetailContent from './IndexDetailContent'

const INTERNAL_API = process.env.INTERNAL_API_URL || 'http://localhost:8000'

export default async function IndexDetailPage({
  params,
}: {
  params: Promise<{ code: string }>
}) {
  const { code } = await params
  const upperCode = code.toUpperCase()

  let indexData
  try {
    const res = await fetch(
      `${INTERNAL_API}/api/v1/market-data/indices/${upperCode}`,
      { cache: 'no-store' }
    )
    if (!res.ok) notFound()
    indexData = await res.json()
  } catch {
    notFound()
  }

  return (
    <PlanGate required="premium" feature="ASX Index Detail">
      <IndexDetailContent initialData={indexData} code={upperCode} />
    </PlanGate>
  )
}
