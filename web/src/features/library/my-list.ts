import { createSignal } from "solid-js";

const MY_LIST_STORAGE_KEY = "anisource_my_list_v1";

export interface MyListRecord {
  anilistId: number;
  addedAt: number;
}

function readMyList(): Record<string, MyListRecord> {
  try {
    const raw = localStorage.getItem(MY_LIST_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    return parsed;
  } catch {
    return {};
  }
}

function writeMyList(data: Record<string, MyListRecord>): void {
  try {
    localStorage.setItem(MY_LIST_STORAGE_KEY, JSON.stringify(data));
    setListSignal(Object.values(data).sort((a, b) => b.addedAt - a.addedAt));
    window.dispatchEvent(new CustomEvent("anisource_my_list_change"));
  } catch {
    // Storage unavailable
  }
}

const initialList = Object.values(readMyList()).sort((a, b) => b.addedAt - a.addedAt);
export const [myListSignal, setListSignal] = createSignal<MyListRecord[]>(initialList);

export function isInMyList(anilistId: number): boolean {
  const map = readMyList();
  return Boolean(map[String(anilistId)]);
}

export function addToMyList(anilistId: number): void {
  const map = readMyList();
  map[String(anilistId)] = {
    anilistId,
    addedAt: Date.now(),
  };
  writeMyList(map);
}

export function removeFromMyList(anilistId: number): void {
  const map = readMyList();
  delete map[String(anilistId)];
  writeMyList(map);
}

export function toggleMyList(anilistId: number): boolean {
  if (isInMyList(anilistId)) {
    removeFromMyList(anilistId);
    return false;
  } else {
    addToMyList(anilistId);
    return true;
  }
}

export function getMyListIds(): number[] {
  return myListSignal().map((item) => item.anilistId);
}
