import {
  Children,
  isValidElement,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import { CaretDown, Check, MagnifyingGlass } from "@phosphor-icons/react";

type Props = {
  value?: string | number;
  onValueChange: (value: string) => void;
  children: ReactNode;
  disabled?: boolean;
  "aria-label"?: string;
  className?: string;
};
export function Select({
  value,
  onValueChange,
  children,
  disabled,
  "aria-label": label = "选择选项",
  className = "",
}: Props) {
  const options = Children.toArray(children)
    .filter(isValidElement)
    .map((child) => {
      const p = child.props as {
        value?: string | number;
        children: ReactNode;
        disabled?: boolean;
      };
      const text = Children.toArray(p.children).join("");
      return {
        value: String(p.value ?? text),
        label: text,
        disabled: p.disabled,
      };
    });
  const [open, setOpen] = useState(false),
    [query, setQuery] = useState(""),
    [active, setActive] = useState(0);
  const [position, setPosition] = useState<CSSProperties>({
    top: 0,
    left: 0,
    width: 0,
    maxHeight: 320,
  });
  const root = useRef<HTMLDivElement>(null),
    trigger = useRef<HTMLButtonElement>(null),
    search = useRef<HTMLInputElement>(null),
    list = useRef<HTMLDivElement>(null);
  const id = useId();
  const shown = options.filter((o) =>
    o.label.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  const close = (restore = false) => {
    setOpen(false);
    if (restore) trigger.current?.focus();
  };
  function place() {
    const r = trigger.current!.getBoundingClientRect();
    const below = window.innerHeight - r.bottom - 16,
      above = r.top - 16;
    const downward = below >= 200 || below >= above;
    setPosition({
      top: downward ? r.bottom + 8 : undefined,
      bottom: downward ? undefined : window.innerHeight - r.top + 8,
      left: Math.max(8, Math.min(r.left, window.innerWidth - r.width - 8)),
      width: Math.min(r.width, window.innerWidth - 16),
      maxHeight: Math.max(120, Math.min(340, downward ? below : above)),
    });
  }
  function show() {
    if (disabled) return;
    place();
    setQuery("");
    setActive(
      Math.max(
        0,
        options.findIndex((o) => o.value === String(value)),
      ),
    );
    setOpen(true);
  }
  useEffect(() => {
    if (!open) return;
    search.current?.focus();
    const outside = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) close();
    };
    const resize = () => close();
    const observer = new ResizeObserver(place);
    observer.observe(trigger.current!);
    const dialog = root.current?.closest("dialog");
    if (dialog) observer.observe(dialog);
    const scroll = (e: Event) => {
      if (
        !(e.target instanceof Element) ||
        !e.target.closest(".select-popover")
      )
        place();
    };
    document.addEventListener("scroll", scroll, true);
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", resize);
    return () => {
      observer.disconnect();
      document.removeEventListener("scroll", scroll, true);
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", resize);
    };
  }, [open]);
  useEffect(() => {
    list.current
      ?.querySelector(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);
  function choose(index: number) {
    const o = shown[index];
    if (o && !o.disabled) {
      onValueChange(o.value);
      close(true);
    }
  }
  function keyboard(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close(true);
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) =>
        Math.max(
          0,
          Math.min(shown.length - 1, a + (e.key === "ArrowDown" ? 1 : -1)),
        ),
      );
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(Math.max(0, shown.length - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(active);
    } else if (e.key === "Tab") close(true);
  }
  return (
    <div className={`neo-select ${className}`} ref={root}>
      <button
        ref={trigger}
        type="button"
        className="select-trigger"
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-haspopup="listbox"
        disabled={disabled}
        onClick={() => (open ? close() : show())}
        onKeyDown={(e) => {
          if (["ArrowDown", "ArrowUp"].includes(e.key)) {
            e.preventDefault();
            show();
          }
        }}
      >
        <span>
          {options.find((o) => o.value === String(value))?.label ||
            options[0]?.label ||
            "请选择"}
        </span>
        <CaretDown size={18} weight="bold" />
      </button>
      {open && (
        <div className="select-popover" style={position}>
          <div className="select-search">
            <MagnifyingGlass size={18} />
            <input
              ref={search}
              aria-label={`搜索${label}`}
              role="combobox"
              aria-expanded="true"
              aria-controls={id}
              aria-activedescendant={
                shown[active] ? `${id}-${active}` : undefined
              }
              value={query}
              placeholder="输入关键词筛选"
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
              }}
              onKeyDown={keyboard}
            />
          </div>
          <div
            ref={list}
            id={id}
            role="listbox"
            aria-label={label}
            className="select-options"
          >
            {shown.map((o, i) => (
              <button
                type="button"
                role="option"
                aria-selected={o.value === String(value)}
                disabled={o.disabled}
                id={`${id}-${i}`}
                data-index={i}
                tabIndex={-1}
                className={active === i ? "highlighted" : ""}
                key={o.value}
                onMouseMove={() => setActive(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(i)}
              >
                <span>{o.label}</span>
                {o.value === String(value) && <Check size={18} weight="bold" />}
              </button>
            ))}
            {!shown.length && <p role="status">没有匹配的选项</p>}
          </div>
        </div>
      )}
    </div>
  );
}
