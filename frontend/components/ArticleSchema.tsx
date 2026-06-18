interface ArticleSchemaProps {
  headline: string
  description: string
  url: string
  datePublished?: string
  dateModified?: string
  articleSection?: string
}

export default function ArticleSchema({
  headline,
  description,
  url,
  datePublished,
  dateModified,
  articleSection,
}: ArticleSchemaProps) {
  const today = new Date().toISOString().split('T')[0]
  const schema: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    '@id': `${url}#article`,
    headline,
    description,
    datePublished: datePublished ?? today,
    dateModified: dateModified ?? today,
    author: { '@id': 'https://asxscreener.com.au/#organization' },
    publisher: { '@id': 'https://asxscreener.com.au/#organization' },
    mainEntityOfPage: { '@type': 'WebPage', '@id': url },
    isPartOf: { '@id': 'https://asxscreener.com.au/#website' },
  }
  if (articleSection) schema.articleSection = articleSection

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  )
}
