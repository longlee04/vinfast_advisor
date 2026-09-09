export const CONSULTATION_OPENING =
  "Chào anh/chị, em là trợ lý tư vấn xe điện. Anh/chị đang cần tìm loại xe nào ạ?";

export const NO_ANSWER_FALLBACK =
  "Em chưa hỗ trợ được yêu cầu này. Anh/chị thử diễn đạt lại giúp em nhé.";

export function recommendationIntro(
  text: string,
  vehicleNames: readonly string[],
): string | null {
  const firstLine = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);
  if (!firstLine || /^(?:[-*]|\d+[.)])\s/.test(firstLine)) return null;
  const normalized = firstLine.toLocaleLowerCase("vi-VN");
  if (
    vehicleNames.some((name) =>
      normalized.includes(name.trim().toLocaleLowerCase("vi-VN")),
    )
  ) {
    return null;
  }
  return firstLine;
}
