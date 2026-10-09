"use client";

import { createContext, type ReactNode, useContext, useState } from "react";
import { useStore } from "zustand";
import { type Api, createApi } from "@/lib/api/client";
import { type Studio, type StudioStore, createStudioStore } from "./store";

const StudioContext = createContext<StudioStore | null>(null);

/** One store per app; tests pass their own `api` (or store) to stay isolated. */
export function StudioProvider({
  children,
  api,
  store,
}: {
  children: ReactNode;
  api?: Api;
  store?: StudioStore;
}) {
  const [value] = useState(() => store ?? createStudioStore(api ?? createApi()));
  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
}

export function useStudio<T>(select: (studio: Studio) => T): T {
  const store = useContext(StudioContext);
  if (!store) {
    throw new Error("useStudio needs a StudioProvider");
  }
  return useStore(store, select);
}
