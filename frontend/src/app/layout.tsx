import type { Metadata, Viewport } from "next";
import { Inter, Instrument_Serif } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const serif = Instrument_Serif({ variable: "--font-instrument", subsets: ["latin"], weight: "400", style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: { default: "Nazar Rakho", template: "%s · Nazar Rakho" },
  description: "You live your life. Nazar keeps an eye. An AI monitor for flight fares, stocks and government job notices, inside your family group chat.",
  applicationName: "Nazar Rakho",
  appleWebApp: { capable: true, title: "Nazar Rakho", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: "#F9F8F5",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${serif.variable} h-full antialiased`}>
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
