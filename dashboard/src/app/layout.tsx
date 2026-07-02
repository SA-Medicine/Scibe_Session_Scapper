import type { Metadata } from "next";
import { Inter, Geist_Mono } from "next/font/google";
import "./globals.css";
import { NavSidebar } from "@/components/NavSidebar";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Heidi Archive — Session Management Platform",
  description: "Production-grade archival platform for Heidi Health Scribe sessions",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${geistMono.variable} h-full dark`}>
      <body className="h-screen flex overflow-hidden">
        <NavSidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Top header bar */}
          <header className="flex-shrink-0 flex items-center justify-between px-6 py-3 border-b border-[var(--color-surface-border)] bg-[var(--color-surface-1)]/80 backdrop-blur-sm z-10">
            <div className="flex items-center gap-3">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse-dot" title="System online" />
              <span className="text-xs text-[var(--color-text-secondary)] font-medium tracking-wide">
                HEIDI ARCHIVE PLATFORM
              </span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-xs text-[var(--color-text-muted)]">
                {new Date().toLocaleDateString("en-AU", { weekday: "short", year: "numeric", month: "short", day: "numeric" })}
              </span>
              <a
                href="/api/scraper-logs"
                target="_blank"
                className="text-xs text-[var(--color-brand-400)] hover:text-[var(--color-brand-200)] transition-colors"
              >
                Raw Logs ↗
              </a>
            </div>
          </header>

          {/* Main content */}
          <main className="flex-1 overflow-y-auto p-6">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
