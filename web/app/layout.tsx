import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Mundial Intel 2026',
  description:
    'Análisis y value bets para el Mundial 2026 con modelo Elo + Dixon-Coles',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="es">
      <body className="min-h-screen bg-white font-sans antialiased">
        {children}
      </body>
    </html>
  )
}
