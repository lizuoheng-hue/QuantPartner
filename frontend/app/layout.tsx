import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuantPartner 量化伴侣",
  description: "把模糊的交易想法变成可验证、可理解、可迭代的策略假设。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
