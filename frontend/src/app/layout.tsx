import "./globals.css";
import type { Metadata } from "next";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "AgriVision AI - Satellite-Powered Agricultural Intelligence",
  description: "Parcel detection and Paddy/Banana crop classification for Tirunelveli district.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <div className="flex h-screen flex-col">
          <Navbar />
          <main className="min-h-0 flex-1 overflow-auto">{children}</main>
        </div>
      </body>
    </html>
  );
}
