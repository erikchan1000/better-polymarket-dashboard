import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Polymarket US Dashboard",
  description: "Order, position and trade data grouped by event and contract.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-surface-950 text-gray-200 antialiased">
        {children}
      </body>
    </html>
  );
}
