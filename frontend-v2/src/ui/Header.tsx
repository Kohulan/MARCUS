import { faGithub } from "@fortawesome/free-brands-svg-icons";
import { faArrowRight, faCircleInfo } from "@fortawesome/free-solid-svg-icons";
import { useEffect, useRef } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import Icon from "./Icon";
import "./ui.css";

/**
 * The "Waterline" nav: a glass pill whose marked item is a drop of green water. The drop
 * stretches to the item under the pointer or focus, then settles with a ripple, and rests on
 * the current page's item (none on the other pages). Everything it moves is two custom
 * properties set through the CSSOM (style.setProperty: allowed under style-src 'self', unlike
 * a style attribute) and three classes; the look is all in ui.css. CSS only, no WebGL.
 */
type Drop = { lastLeft: number | null; settle: number };

function ripple(wl: HTMLElement) {
  wl.classList.remove("is-settling");
  void wl.offsetWidth; // restart the keyframes
  wl.classList.add("is-settling");
}

function place(wl: HTMLElement, drop: Drop, el: HTMLElement) {
  const left = el.offsetLeft;
  const right = wl.clientWidth - left - el.offsetWidth;
  const shown = wl.classList.contains("has-drop");
  wl.dataset.dir =
    !shown || drop.lastLeft === null ? "none" : left > drop.lastLeft ? "right" : "left";
  const moved = left !== drop.lastLeft || !shown;
  drop.lastLeft = left;
  wl.style.setProperty("--wl-l", `${left}px`);
  wl.style.setProperty("--wl-r", `${right}px`);
  wl.classList.add("has-drop");
  if (moved) {
    window.clearTimeout(drop.settle);
    drop.settle = window.setTimeout(() => ripple(wl), shown ? 380 : 120);
  }
}

/** Back to the current page's item, or no drop where the page has none. */
function rest(wl: HTMLElement, drop: Drop) {
  const current = wl.querySelector<HTMLElement>('[aria-current="page"]');
  if (current) {
    place(wl, drop, current);
  } else {
    wl.classList.remove("has-drop");
    window.clearTimeout(drop.settle);
  }
}

/** The mark and the nav float free above the page's ruled sheet. */
export default function Header() {
  const { pathname } = useLocation();
  const here = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const nav = useRef<HTMLElement>(null);
  const drop = useRef<Drop>({ lastLeft: null, settle: 0 });

  // After each page change, once the fonts have set the items' widths, and on resize.
  useEffect(() => {
    const wl = nav.current;
    if (!wl) return;
    const state = drop.current;
    let live = true;
    rest(wl, state);
    void document.fonts?.ready.then(() => {
      if (live) rest(wl, state);
    });
    const onResize = () => {
      if (!wl.classList.contains("has-drop")) return;
      wl.dataset.dir = "none";
      rest(wl, state);
    };
    window.addEventListener("resize", onResize);
    return () => {
      live = false;
      window.removeEventListener("resize", onResize);
      window.clearTimeout(state.settle);
    };
  }, [here]);

  const toItem = (e: { currentTarget: HTMLElement }) => {
    if (nav.current) place(nav.current, drop.current, e.currentTarget);
  };

  // Arrow keys, Home and End move focus along the three items.
  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    const items = [...e.currentTarget.querySelectorAll<HTMLElement>(".wl__item")];
    const i = items.indexOf(document.activeElement as HTMLElement);
    if (i < 0) return;
    const to =
      e.key === "ArrowRight"
        ? i + 1
        : e.key === "ArrowLeft"
          ? i - 1
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? items.length - 1
              : -1;
    if (to < 0 || to >= items.length || to === i) return;
    e.preventDefault();
    items[to]?.focus();
  };

  const onPointerLeave = (e: PointerEvent<HTMLElement>) => {
    if (!e.currentTarget.contains(document.activeElement)) rest(e.currentTarget, drop.current);
  };

  const onPointerMove = (e: PointerEvent<HTMLElement>) => {
    const wl = e.currentTarget;
    wl.style.setProperty("--wl-mx", `${e.clientX - wl.getBoundingClientRect().left}px`);
  };

  const onBlur = (e: { currentTarget: HTMLElement; relatedTarget: EventTarget | null }) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
      rest(e.currentTarget, drop.current);
    }
  };

  const current = (to: string) => (here === to ? "page" : undefined);

  return (
    <header className="site-header">
      <Link to="/" className="site-header__mark">
        <img src="/logo.png" alt="" width="36" height="36" />
        <span className="site-header__word">MARCUS</span>
      </Link>
      <div className="site-header__nav">
        <nav
          ref={nav}
          aria-label="Main"
          className="wl"
          onKeyDown={onKeyDown}
          onPointerLeave={onPointerLeave}
          onPointerMove={onPointerMove}
          onBlur={onBlur}
        >
          <span className="wl__drop" aria-hidden="true">
            <span className="wl__ripple" />
          </span>
          <Link
            className="wl__item"
            to="/about"
            aria-current={current("/about")}
            onPointerEnter={toItem}
            onFocus={toItem}
          >
            <Icon icon={faCircleInfo} />
            About
          </Link>
          <a
            className="wl__item"
            href="https://github.com/Kohulan/MARCUS"
            target="_blank"
            rel="noopener noreferrer"
            onPointerEnter={toItem}
            onFocus={toItem}
          >
            <Icon icon={faGithub} />
            GitHub<span className="visually-hidden"> (opens in a new tab)</span>
          </a>
          <Link
            className="wl__item"
            to="/app"
            aria-current={current("/app")}
            onPointerEnter={toItem}
            onFocus={toItem}
          >
            Open the tool
            <Icon icon={faArrowRight} className="fa--after" />
          </Link>
        </nav>
      </div>
    </header>
  );
}
