import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SmartConvertAI — Industrial Document Scanner",
  description:
    "Upload photos of documents, auto-detect borders, de-skew, apply Xerox-style B&W or Smart Color filters and export ultra-light PDFs with crystal-clear text.",
};

export const viewport: Viewport = {
  themeColor: "#070b14",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
