import { useEffect } from "react";

/** Register agent-panel keyboard shortcuts. Returns nothing; effects manage
 * lifecycle.
 *
 * Shortcuts:
 *   /  or ⌘K   — focus search input (testid agent-filter-search)
 *   j / k      — next / previous ticket in current visible list
 *   Enter      — open detail of focused ticket
 *   Escape     — close detail / back to bandeja
 *   ?          — toggle help modal
 */
export function useAgentShortcuts({
  onSearch, onNext, onPrev, onOpen, onClose, onHelp,
} = {}) {
  useEffect(() => {
    function handler(e) {
      // Ignore when user is typing in an input/textarea/contentEditable.
      const tag = (e.target?.tagName || "").toLowerCase();
      const editable = tag === "input" || tag === "textarea"
        || e.target?.isContentEditable;

      // ⌘K / Ctrl+K
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onSearch?.();
        return;
      }
      if (editable) {
        // Si está escribiendo y aprieta Esc, soltamos el foco para que el
        // próximo shortcut global (?, j, k, etc.) funcione.
        if (e.key === "Escape" && e.target?.blur) {
          e.target.blur();
        }
        return;
      }

      switch (e.key) {
        case "/":
          e.preventDefault(); onSearch?.(); break;
        case "j":
          e.preventDefault(); onNext?.(); break;
        case "k":
          e.preventDefault(); onPrev?.(); break;
        case "Enter":
          e.preventDefault(); onOpen?.(); break;
        case "Escape":
          onClose?.(); break;
        case "?":
          e.preventDefault(); onHelp?.(); break;
        default:
          break;
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onSearch, onNext, onPrev, onOpen, onClose, onHelp]);
}

export const SHORTCUTS_HELP = [
  { keys: ["⌘", "K"], desc: "Buscar tickets" },
  { keys: ["/"], desc: "Buscar (alternativo)" },
  { keys: ["j"], desc: "Siguiente ticket" },
  { keys: ["k"], desc: "Anterior ticket" },
  { keys: ["Enter"], desc: "Abrir detalle" },
  { keys: ["Esc"], desc: "Volver a bandeja" },
  { keys: ["?"], desc: "Mostrar esta ayuda" },
];
