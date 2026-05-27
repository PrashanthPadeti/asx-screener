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
  description: 'Screen ASX stocks with franking credits, mining & REIT depth, and AI insights',
  alternates: {
    canonical: 'https://asxscreener.com.au',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-50 min-h-screen overflow-x-hidden`}>
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
