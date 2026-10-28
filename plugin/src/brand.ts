import logoSvg from "../../assets/prelo-logo.svg";

// Heavy PREL with the O inside a yellow stone, from the same family as samuhlo/anaco-ob.
// Standalone SVGs follow the OS theme; embedded logos inherit Obsidian's theme.
export function appendPreloLogo(parent: HTMLElement) {
  const parsed = new DOMParser().parseFromString(logoSvg, "image/svg+xml");
  const logo = document.importNode(parsed.documentElement, true);
  logo.querySelector("style")?.remove();
  // Inline copies share the document: the file's title/desc ids would repeat with several open views.
  logo.querySelectorAll("title, desc").forEach(node => node.remove());
  logo.removeAttribute("aria-labelledby");
  logo.setAttribute("aria-label", "Prelo");
  parent.appendChild(logo);
  return logo;
}
