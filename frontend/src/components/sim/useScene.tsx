"use client";

import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useStore } from "zustand";
import type { Edge } from "@/lib/api/client";
import { createAnimationController } from "@/lib/sim/controller";
import type { Geometry } from "@/lib/sim/geometry";
import { type Scene, playStep } from "@/lib/sim/timeline";
import { LONG_WORD, type SimulatorStore, stepAt } from "@/lib/studio/simulator";
import { Dropout, Ripple } from "./Effects";
import { type Signal, Token, createSignal } from "./Token";

type Effect = { key: number; state: string; kind: "ripple" | "pulse" | "drop" };
type Tokens = { key: number; ids: string[]; progress: Signal };

const RIPPLE_MS = 500;
const PULSE_MS = 900;
const NO_TOKENS = { progress: () => undefined, clear: () => undefined };

/**
 * The step animation drawn on the page: tokens and effects in a layer portalled into
 * the Graphviz group, state and witness classes on the diagram's own elements, and the
 * head, settled set and verdict in the store. Without a diagram only the store changes.
 */
export function useScene(
  geometry: Geometry | null,
  idMap: Readonly<Record<string, string>>,
  accepting: ReadonlySet<string>,
  store: SimulatorStore,
): { scene: Scene; layer: ReactNode } {
  const [tokens, setTokens] = useState<Tokens | null>(null);
  const [effects, setEffects] = useState<Effect[]>([]);
  const speed = useStore(store, (state) => state.speed);
  const keys = useRef(0);
  const witnessShown = useRef(new Set<string>());

  const scene = useMemo<Scene>(() => {
    const drawn = (edges: readonly Edge[]): string[] =>
      edges.flatMap(([q, a, r]) => {
        const id = idMap[`${q}|${a}|${r}`];
        return id !== undefined && geometry?.edges.has(id) ? [id] : [];
      });

    const add = (states: readonly string[], kind: Effect["kind"]) => {
      const shown = states.filter((state) => geometry?.states.has(state));
      if (shown.length > 0) {
        setEffects((list) => [
          ...list,
          ...shown.map((state) => ({ key: ++keys.current, state, kind })),
        ]);
      }
    };

    const clearWitness = () => {
      for (const id of witnessShown.current) {
        const shape = geometry?.edges.get(id);
        shape?.group.classList.remove("is-witness");
        shape?.path.style.removeProperty("stroke-dasharray");
        shape?.path.style.removeProperty("stroke-dashoffset");
      }
      witnessShown.current.clear();
    };

    return {
      read: (index) => store.getState().show({ head: index }),

      tokens: (edges) => {
        const ids = [...new Set(drawn(edges))];
        if (ids.length === 0) {
          return NO_TOKENS;
        }
        const progress = createSignal(0);
        const key = ++keys.current;
        setTokens({ key, ids, progress });
        return {
          progress: progress.set,
          clear: () =>
            setTokens((current) => (current?.key === key ? null : current)),
        };
      },

      ripple: (states) => add(states, "ripple"),

      settle: (index, active, dropped, instant) => {
        clearWitness();
        for (const [name, shape] of geometry?.states ?? []) {
          shape.group.classList.toggle("is-active", active.includes(name));
        }
        if (!instant) {
          add(dropped, "drop");
        }
        store.getState().show({ settled: { index, active: [...active] } });
      },

      verdict: (accepted, instant) => {
        store.getState().show({ verdict: accepted });
        if (accepted && !instant) {
          const active = store.getState().settled?.active ?? [];
          add(
            active.filter((state) => accepting.has(state)),
            "pulse",
          );
        }
      },

      // Edge k of n draws during the k-th n-th of the progress, so the path grows from q₀.
      witness: (progress) => {
        const ids = drawn(store.getState().trace?.witness ?? []);
        const reach = new Map<string, number>();
        ids.forEach((id, k) => {
          const local = Math.min(Math.max(progress * ids.length - k, 0), 1);
          reach.set(id, Math.max(reach.get(id) ?? 0, local));
        });
        for (const [id, local] of reach) {
          const shape = geometry?.edges.get(id);
          if (!shape || local === 0) {
            continue;
          }
          witnessShown.current.add(id);
          shape.group.classList.add("is-witness");
          shape.path.style.strokeDasharray = `${shape.length}`;
          shape.path.style.strokeDashoffset = `${shape.length * (1 - local)}`;
        }
      },

      interrupt: () => {
        setTokens(null);
        setEffects((list) => (list.length === 0 ? list : []));
      },
    };
  }, [geometry, idMap, accepting, store]);

  const finish = (key: number) =>
    setEffects((list) => list.filter((effect) => effect.key !== key));

  const layer = geometry
    ? createPortal(
        <g className="sim-layer" aria-hidden>
          {effects.map((effect) => {
            const shape = geometry.states.get(effect.state);
            if (!shape) {
              return null;
            }
            return effect.kind === "drop" ? (
              <Dropout
                key={effect.key}
                shape={shape}
                onEnd={() => finish(effect.key)}
              />
            ) : (
              <Ripple
                key={effect.key}
                shape={shape}
                variant={effect.kind}
                duration={
                  (effect.kind === "pulse" ? PULSE_MS : RIPPLE_MS) / speed
                }
                onEnd={() => finish(effect.key)}
              />
            );
          })}
          {tokens?.ids.map((id) => (
            <Token
              key={`${tokens.key}-${id}`}
              geometry={geometry}
              pathId={id}
              progress={tokens.progress}
            />
          ))}
        </g>,
        geometry.layer,
      )
    : null;

  return { scene, layer };
}

/**
 * Plays the current step whenever the position, the trace or a control changes, and
 * moves playback on when a step ends. A change of diagram alone redraws instantly.
 */
export function usePlayer(scene: Scene, store: SimulatorStore): void {
  const controller = useMemo(() => createAnimationController(), []);
  const trace = useStore(store, (state) => state.trace);
  const seq = useStore(store, (state) => state.seq);
  const played = useRef(-1);

  useEffect(() => {
    const state = store.getState();
    const step = stepAt(trace, state.position);
    if (!trace || !step) {
      return;
    }
    const sceneOnly = played.current === seq;
    played.current = seq;
    const last = state.position === trace.total - 1;
    playStep(
      controller,
      scene,
      {
        step,
        previous:
          state.position > 0
            ? (stepAt(trace, state.position - 1)?.after ?? null)
            : null,
        last,
        accepted: trace.accepted,
        witness: state.showWitness && trace.witness !== null,
        speed: state.speed,
        // trace.total counts step 0 as well as one step per symbol.
        instant:
          sceneOnly || state.motion === "jump" || trace.total - 1 > LONG_WORD,
        hold: state.playing && !last,
      },
      () => store.getState().advance(),
    );
    return () => controller.cancel();
  }, [controller, scene, store, trace, seq]);
}
