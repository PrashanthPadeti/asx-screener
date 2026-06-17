interface ArticleSchemaProps {
  headline: string
  description: string
  url: string
  datePublished?: string
  dateModified?: string
}

export default function ArticleSchema({
  headline,
  description,
  url,
  datePublished = '2026-06-17',
  dateModified = '2026-06-17',
}: ArticleSchemaProps) {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline,
    description,
    url,
    datePublished,
    dateModified,
    author: {
      '@type': 'Organization',
      name: 'ASX Screener',
      url: 'https://asxscreener.com.au',
      '@id': 'https://asxscreener.com.au/#organization',
    },
    publisher: {
      '@type': 'Organization',
      name: 'ASX Screener',
      url: 'https://asxscreener.com.au',
      '@id': 'https://asxscreener.com.au/#organization',
    },
    mainEntityOfPage: {
      '@type': 'WebPage',
      '@id': url,
    },
    isPartOf: { '@id': 'https://asxscreener.com.au/#website' },
  }

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  )
}
