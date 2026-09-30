import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "../components/AuthProvider";
export const metadata: Metadata = { title: "Verba | Speak with confidence", description: "British English speaking practice for educators" };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body><AuthProvider>{children}</AuthProvider></body></html>; }
