import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "matdoria",
  description: "미쉐린과 서울미래유산 식당을 카카오맵에서 보는 개인 맛집 지도",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
