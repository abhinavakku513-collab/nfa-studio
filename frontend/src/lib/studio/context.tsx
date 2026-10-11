"use client";

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import { useStore } from "zustand";
import { type Api, createApi, wakeServer } from "@/lib/api/client";
import { type Wake, type WakeStore, createWakeStore } from "@/lib/api/wake";
import { type Explore, type ExploreStore, createExploreStore } from "./explore";
import {
  type Simulator,
  type SimulatorStore,
  createSimulatorStore,
} from "./simulator";
import { type Studio, type StudioStore, createStudioStore } from "./store";

type Stores = {
  studio: StudioStore;
  explore: ExploreStore;
  simulator: SimulatorStore;
  wake: WakeStore;
};

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
    const wake = createWakeStore();
    const client = api ?? createApi({ retry: { listener: wake.getState() } });
    return {
      studio: createStudioStore(client),
      explore: createExploreStore(client),
      simulator: createSimulatorStore(client),
      wake,
    };
  });
  const ownClient = !api && !stores;
  useEffect(() => {
    if (ownClient) {
      wakeServer();
    }
  }, [ownClient]);
  return (
    <StoresContext.Provider value={value}>{children}</StoresContext.Provider>
  );
}

function useStores(): Stores {
  const stores = useContext(StoresContext);
  if (!stores) {
    throw new Error("The studio hooks need a StudioProvider");
  }
  return stores;
}

export function useStudio<T>(select: (studio: Studio) => T): T {
  return useStore(useStores().studio, select);
}

export function useExplore<T>(select: (explore: Explore) => T): T {
  return useStore(useStores().explore, select);
}

export function useSimulator<T>(select: (simulator: Simulator) => T): T {
  return useStore(useStores().simulator, select);
}

export function useWake<T>(select: (wake: Wake) => T): T {
  return useStore(useStores().wake, select);
}

/** The simulator store itself, for the animation code that reads it between renders. */
export function useSimulatorStore(): SimulatorStore {
  return useStores().simulator;
}
