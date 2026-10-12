import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Noto_Sans_Math } from "next/font/google";
import { THEME_SCRIPT } from "@/lib/theme";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "greek"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin", "greek"],
});

// Fallback for ε δ Σ ∅ and subscripts (spec §12.2). Google publishes no subsets for this
// family, so next/font loads it without a preload link.
const notoSansMath = Noto_Sans_Math({
  variable: "--font-noto-sans-math",
  weight: "400",
});

export const metadata: Metadata = {
  title: "NFA Studio",
  description: "Describe a regular language and get a verified NFA.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // The theme script sets data-theme before React hydrates, so the attribute differs
    // from the server render by design.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${jetbrainsMono.variable} ${notoSansMath.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
