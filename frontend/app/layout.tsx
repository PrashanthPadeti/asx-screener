import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Navbar from '@/components/Navbar'
import Footer from '@/components/Footer'
import CookieConsent from '@/components/CookieConsent'
import { AuthProvider } from '@/lib/auth'
import { ClientGuard } from '@/components/ClientGuard'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  metadataBase: new URL('https://asxscreener.com.au'),
  title: {
    default:  'ASX Screener — Australian Stock Screener',
    template: '%s | ASX Screener',
  },
  description: 'Screen ASX stocks with franking credits, mining & REIT depth, and AI insights. Free for Australian investors.',
  alternates: {
    canonical: 'https://asxscreener.com.au',
  },
  openGraph: {
    type:        'website',
    siteName:    'ASX Screener',
    title:       'ASX Screener — Australian Stock Screener',
    description: 'Screen ASX stocks with franking credits, mining & REIT depth, and AI insights. Free for Australian investors.',
    url:         'https://asxscreener.com.au',
    images: [{ url: '/og-image.png', width: 1200, height: 630, alt: 'ASX Screener — Australian Stock Screener' }],
  },
  twitter: {
    card:        'summary_large_image',
    title:       'ASX Screener — Australian Stock Screener',
    description: 'Screen ASX stocks with franking credits, mining & REIT depth, and AI insights. Free for Australian investors.',
    images:      ['/og-image.png'],
  },
  verification: {
    google: '42Vl_6jkLmVW1klkNqSSjfse1wxr0sNN8NkUXaiqGwQ',
  },
}

const siteSchema = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'Organization',
      '@id': 'https://asxscreener.com.au/#organization',
      name: 'ASX Screener',
      url: 'https://asxscreener.com.au',
      description: 'Australian stock screening and research platform with franking credits, mining & REIT depth, and AI insights.',
      foundingLocation: { '@type': 'Country', name: 'Australia' },
    },
    {
      '@type': 'WebSite',
      '@id': 'https://asxscreener.com.au/#website',
      url: 'https://asxscreener.com.au',
      name: 'ASX Screener',
      publisher: { '@id': 'https://asxscreener.com.au/#organization' },
    },
    {
      '@type': 'SoftwareApplication',
      '@id': 'https://asxscreener.com.au/#app',
      name: 'ASX Screener',
      applicationCategory: 'FinanceApplication',
      operatingSystem: 'Web',
      url: 'https://asxscreener.com.au',
      description: 'Stock screening and research tool for ASX-listed companies. Filter by PE ratio, dividend yield, franking credits, ROE, and 80+ financial metrics.',
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'AUD', description: 'Free plan available' },
    },
  ],
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-50 min-h-screen overflow-x-hidden`}>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(siteSchema) }}
        />
        <AuthProvider>
          <Navbar />
          <main className="max-w-screen-2xl mx-auto px-4 py-6">
            <ClientGuard>
              {children}
            </ClientGuard>
          </main>
          <Footer />
          <CookieConsent />
        </AuthProvider>
      </body>
    </html>
  )
}
