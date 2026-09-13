export function normalizeTitle(raw: string): string {
  if (!raw) return "";

  let title = raw
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "") // strip diacritics
    .toLowerCase();

  // Normalize season/cour notations to standard tokens
  title = title
    .replace(/\b1st\s+season\b/gi, "season 1")
    .replace(/\b2nd\s+season\b/gi, "season 2")
    .replace(/\b3rd\s+season\b/gi, "season 3")
    .replace(/\b4th\s+season\b/gi, "season 4")
    .replace(/\b5th\s+season\b/gi, "season 5")
    .replace(/\bsecond\s+season\b/gi, "season 2")
    .replace(/\bthird\s+season\b/gi, "season 3")
    .replace(/\bfourth\s+season\b/gi, "season 4")
    .replace(/\bfifth\s+season\b/gi, "season 5")
    .replace(/\bthe\s+final\s+season\b/gi, "final season")
    .replace(/\bpart\s+(\d+)\b/gi, "part $1")
    .replace(/\bcour\s+(\d+)\b/gi, "cour $1")
    .replace(/\bii\b/gi, "2")
    .replace(/\biii\b/gi, "3")
    .replace(/\biv\b/gi, "4")
    .replace(/\bv\b/gi, "5");

  // Remove punctuation & special chars, keeping alphanumeric and spaces
  title = title.replace(/[^a-z0-9\s]/g, " ");

  // Collapse spaces
  title = title.replace(/\s+/g, " ").trim();

  return title;
}

export function extractSeasonNumber(title: string): number | null {
  const norm = normalizeTitle(title);
  const match = norm.match(/\bseason\s+(\d+)\b/);
  if (match) return parseInt(match[1], 10);
  const matchPart = norm.match(/\bpart\s+(\d+)\b/);
  if (matchPart) return parseInt(matchPart[1], 10);
  const matchCour = norm.match(/\bcour\s+(\d+)\b/);
  if (matchCour) return parseInt(matchCour[1], 10);

  // Standalone numbers at end of title like "mob psycho 100 2" or "k-on 2"
  const trailingNum = norm.match(/\s([2-9])$/);
  if (trailingNum) return parseInt(trailingNum[1], 10);

  return null;
}

export function levenshteinDistance(s1: string, s2: string): number {
  if (s1 === s2) return 0;
  if (!s1.length) return s2.length;
  if (!s2.length) return s1.length;

  const v0 = new Array(s2.length + 1).fill(0);
  const v1 = new Array(s2.length + 1).fill(0);

  for (let i = 0; i <= s2.length; i++) {
    v0[i] = i;
  }

  for (let i = 0; i < s1.length; i++) {
    v1[0] = i + 1;
    for (let j = 0; j < s2.length; j++) {
      const cost = s1[i] === s2[j] ? 0 : 1;
      v1[j + 1] = Math.min(v1[j] + 1, v0[j + 1] + 1, v0[j] + cost);
    }
    for (let j = 0; j <= s2.length; j++) {
      v0[j] = v1[j];
    }
  }

  return v1[s2.length];
}

export function similarityRatio(s1: string, s2: string): number {
  const n1 = normalizeTitle(s1);
  const n2 = normalizeTitle(s2);
  if (!n1 || !n2) return 0;
  if (n1 === n2) return 1.0;

  const maxLen = Math.max(n1.length, n2.length);
  if (maxLen === 0) return 1.0;
  const dist = levenshteinDistance(n1, n2);
  return 1 - dist / maxLen;
}

export function tokenJaccardSimilarity(s1: string, s2: string): number {
  const t1 = new Set(normalizeTitle(s1).split(/\s+/).filter(Boolean));
  const t2 = new Set(normalizeTitle(s2).split(/\s+/).filter(Boolean));
  if (!t1.size || !t2.size) return 0;

  let intersection = 0;
  for (const token of t1) {
    if (t2.has(token)) intersection++;
  }
  const union = t1.size + t2.size - intersection;
  return intersection / union;
}
