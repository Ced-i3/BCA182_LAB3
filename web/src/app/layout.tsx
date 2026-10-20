import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Activity Monitor | BCA152 Lab 3",
  description: "Experimental activity and motion monitoring for the RT-Spark laboratory project.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
