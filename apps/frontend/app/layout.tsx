import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "MarketMind",
  description: "Market intelligence product foundation",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

