import fs from "node:fs";
import path from "node:path";

import { extractCarEditorial, type CarEditorial } from "@/lib/car-editorial";

const DOCUMENTS: Record<string, string> = {
  "vf-2": "VF2.md",
  "vf-3": "VF3.md",
  "vf-5": "VF5.md",
  "vf-6": "VF6.md",
  "vf-mpv-7": "MPV7.md",
  "vf-7": "VF7.md",
  "vf-8": "VF8.md",
  "vf-8-all-new": "VF8_2026.md",
  "vf-9": "VF9.md",
};

/** Read editorial text from the repository's car_pdf corpus at build time. */
export function loadCarEditorial(slug: string): CarEditorial | null {
  const filename = DOCUMENTS[slug];
  if (!filename) return null;
  const filePath = path.join(process.cwd(), "..", "data-p150", "car_pdf", filename);
  return extractCarEditorial(fs.readFileSync(filePath, "utf8"));
}
