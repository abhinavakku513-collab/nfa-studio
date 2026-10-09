"use client";

import { createContext, type ReactNode, useContext, useState } from "react";
import { useStore } from "zustand";
import { type Api, createApi } from "@/lib/api/client";
import { type Explore, type ExploreStore, createExploreStore } from "./explore";
import { type Studio, type StudioStore, createStudioStore } from "./store";

type Stores = { studio: StudioStore; explore: ExploreStore };

const StoresContext = createContext<Stores | null>(null);

/** One set of stores per app; tests pass their own `api` (or stores) to stay isolated. */
export function StudioProvider({
  children,
  api,
  stores,
}: {
  children: ReactNode;
  api?: Api;
  stores?: Stores;
}) {
  const [value] = useState<Stores>(() => {
    if (stores) {
      return stores;
    }
    const client = api ?? createApi();
    return {
      studio: createStudioStore(client),
      explore: createExploreStore(client),
    };
  });
  return (
    <StoresContext.Provider value={value}>{children}</StoresContext.Provider>
  );
}

function useStores(): Stores {
  const stores = useContext(StoresContext);
  if (!stores) {
    throw new Error("useStudio and useExplore need a StudioProvider");
  }
  return stores;
}

export function useStudio<T>(select: (studio: Studio) => T): T {
  return useStore(useStores().studio, select);
}

export function useExplore<T>(select: (explore: Explore) => T): T {
  return useStore(useStores().explore, select);
}
