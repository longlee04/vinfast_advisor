export type CarEditorial = {
  summary: string;
  exterior: string;
  interior: string;
  performance: string;
  safety: string;
  sourceUrl: string | null;
};

function frontmatterValue(markdown: string, key: string): string | null {
  const match = markdown.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
  return match?.[1]?.trim() ?? null;
}

function firstSentences(text: string, count: number): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  const sentences = normalized.match(/[^.!?]+[.!?]+(?:[”"])?/g) ?? [normalized];
  return sentences.slice(0, count).join(" ").replace(/\s+/g, " ").trim();
}

function section(markdown: string, heading: string): string {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return markdown.match(new RegExp(`^## ${escaped}\\s*\\n([\\s\\S]*?)(?=^## |(?![\\s\\S]))`, "m"))?.[1] ?? "";
}

/** Convert one local car document into concise, customer-facing editorial copy. */
export function extractCarEditorial(markdown: string): CarEditorial {
  const overview = markdown.match(/^## Tổng quan\s*\n([\s\S]*?)(?=^## |(?![\s\S]))/m)?.[1] ?? "";
  return {
    summary: firstSentences(overview, 2),
    exterior: firstSentences(section(markdown, "Thiết kế ngoại thất"), 2),
    interior: firstSentences(section(markdown, "Nội thất và tiện nghi"), 2),
    performance: firstSentences(section(markdown, "Khả năng vận hành"), 2),
    safety: firstSentences(section(markdown, "An toàn và hỗ trợ lái"), 2),
    sourceUrl: frontmatterValue(markdown, "source_url"),
  };
}
