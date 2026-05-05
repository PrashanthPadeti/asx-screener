import { notFound } from 'next/navigation'
import { PlanGate } from '@/components/PlanGate'
import FundDetailContent from './FundDetailContent'

const INTERNAL_API = process.env.INTERNAL_API_URL || 'http://localhost:8000'

export default async function FundDetailPage({
  params,
}: {
  params: Promise<{ code: string }>
}) {
  const { code } = await params
  const upperCode = code.toUpperCase()

  let fundData
  try {
    const res = await fetch(
      `${INTERNAL_API}/api/v1/market-data/funds/${upperCode}?days=1825`,
      { cache: 'no-store' }
    )
    if (!res.ok) notFound()
    fundData = await res.json()
  } catch {
    notFound()
  }

  return (
    <PlanGate required="premium" feature="Fund Detail">
      <FundDetailContent initialData={fundData} code={upperCode} />
    </PlanGate>
  )
}
