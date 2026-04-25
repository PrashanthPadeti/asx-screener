import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Navbar from '@/components/Navbar'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'ASX Screener — Australian Stock Screener',
  description: 'Screen ASX stocks with franking credits, mining & REIT depth, and AI insights',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-50 min-h-screen`}>
        <Navbar />
        <main className="max-w-screen-2xl mx-auto px-4 py-6">
          {children}
        </main>
      </body>
    </html>
  )
}
