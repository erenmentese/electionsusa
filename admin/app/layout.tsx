import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ElectionsUSA Yönetim",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />
      </head>
      <body>
        <div className="ribbon" aria-hidden="true" />
        {children}
      </body>
    </html>
  );
}
