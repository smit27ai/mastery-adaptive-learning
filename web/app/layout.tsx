import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mastery - Adaptive Learning",
  description:
    "An adaptive learning engine that infers what you know and chooses what to teach next.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="bg-ink text-white antialiased">{children}</body>
    </html>
  );
}
