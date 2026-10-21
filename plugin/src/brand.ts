import logoSvg from "../../assets/prelo-logo.svg";

// The same faceted crystal and rounded lettering as samuhlo/anaco-ob.
// Standalone SVGs follow the OS theme; embedded logos inherit Obsidian's theme.
export function appendPreloLogo(parent: HTMLElement) {
  const parsed = new DOMParser().parseFromString(logoSvg, "image/svg+xml");
  const logo = document.importNode(parsed.documentElement, true);
  logo.querySelector("style")?.remove();
  parent.appendChild(logo);
  return logo;
}

