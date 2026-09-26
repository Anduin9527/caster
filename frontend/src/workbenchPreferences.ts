import { useEffect, useState, type SetStateAction } from "react";
import { expressionPresets as moods } from "./presentation";
import { readPreference, writePreference } from "./storage";

const ACTIVE_KEY = "caster-live-active-v1";
const optionsKey = (id: string) => `caster-live-options-${id}`;
type Options = {
  step: number;
  outfitIds: string[];
  poseIds: string[];
  expressions: { name: string; prompt: string }[];
  chosenMoods: string[];
};
const strings = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];

export function parseWorkbenchOptions(raw: string | null): Options {
  let saved: Partial<Options> = {};
  try {
    saved = JSON.parse(raw || "null") || {};
  } catch {
    /* use defaults */
  }
  const expressions = [
    ...moods,
    ...(Array.isArray(saved.expressions) ? saved.expressions : []).filter(
      (item) =>
        item &&
        typeof item.name === "string" &&
        typeof item.prompt === "string" &&
        !moods.some((mood) => mood.prompt === item.prompt),
    ),
  ];
  return {
    step:
      Number.isInteger(saved.step) && saved.step! >= 0 && saved.step! <= 5
        ? saved.step!
        : 0,
    outfitIds: strings(saved.outfitIds),
    poseIds: strings(saved.poseIds).filter((id) =>
      /^preset:1[0-9]{2}$/.test(id),
    ),
    expressions,
    chosenMoods: Array.isArray(saved.chosenMoods)
      ? strings(saved.chosenMoods).filter((prompt) =>
          expressions.some((item) => item.prompt === prompt),
        )
      : moods.slice(0, 3).map((mood) => mood.prompt),
  };
}

// Keep ownership and values in one state update; effects never save character A's
// options under character B while a collection of independent setters catches up.
export function useWorkbenchPreferences() {
  const [state, setState] = useState(() => {
    const active = readPreference(ACTIVE_KEY) || "";
    return {
      active,
      ...parseWorkbenchOptions(readPreference(optionsKey(active))),
    };
  });
  const { active } = state;
  useEffect(() => {
    writePreference(ACTIVE_KEY, active);
    if (active) writePreference(optionsKey(active), JSON.stringify(state));
  }, [state, active]);
  function field<K extends keyof Options>(key: K) {
    return (action: SetStateAction<Options[K]>) =>
      setState((current) => {
        if (current.active !== active) return current;
        const value =
          typeof action === "function"
            ? (action as (previous: Options[K]) => Options[K])(current[key])
            : action;
        return value === current[key] ? current : { ...current, [key]: value };
      });
  }
  return {
    ...state,
    setActive(action: SetStateAction<string>, step?: number) {
      setState((current) => {
        const id =
          typeof action === "function" ? action(current.active) : action;
        if (current.active === id)
          return step === undefined ? current : { ...current, step };
        const options = parseWorkbenchOptions(readPreference(optionsKey(id)));
        return {
          active: id,
          ...options,
          ...(step === undefined ? {} : { step }),
        };
      });
    },
    setStep: field("step"),
    setOutfitIds: field("outfitIds"),
    setPoseIds: field("poseIds"),
    setExpressions: field("expressions"),
    setChosenMoods: field("chosenMoods"),
  };
}
