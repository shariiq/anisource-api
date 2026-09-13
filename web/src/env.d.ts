/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ANILIST_ENDPOINT?: string;
  readonly VITE_ANISOURCE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
