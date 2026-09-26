import { useEffect, useRef } from "react";

export function useStepNavigation(step: number) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const nav = ref.current;
    if (!nav) return;
    const reveal = () => {
      const item = nav.querySelector<HTMLElement>('[aria-current="step"]');
      if (!item || nav.scrollWidth <= nav.clientWidth) return;
      const bounds = item.getBoundingClientRect();
      const viewport = nav.getBoundingClientRect();
      nav.scrollLeft +=
        bounds.left - viewport.left - (nav.clientWidth - bounds.width) / 2;
    };
    reveal();
    const observer = new ResizeObserver(reveal);
    observer.observe(nav);
    return () => observer.disconnect();
  }, [step]);
  return ref;
}
