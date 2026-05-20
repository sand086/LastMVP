import { Keyboard, X } from "lucide-react";
import { SHORTCUTS_HELP } from "./shortcuts";

export default function KeyboardShortcutsHelp({ onClose }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-mye-ink/40 backdrop-blur-sm"
         onClick={onClose}
         data-testid="agent-shortcuts-help">
      <div className="bg-white rounded-lg border border-mye-border p-5 w-[420px] space-y-3"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2">
          <Keyboard className="h-4 w-4 text-mye-accent" />
          <h3 className="font-medium text-sm">Atajos de teclado</h3>
          <button onClick={onClose}
                  className="ml-auto rounded-full hover:bg-mye-primary-soft p-1"
                  data-testid="agent-shortcuts-close">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="space-y-1.5">
          {SHORTCUTS_HELP.map((s) => (
            <div key={s.desc} className="flex items-center justify-between text-xs">
              <span className="text-mye-ink-muted">{s.desc}</span>
              <span className="flex items-center gap-1">
                {s.keys.map((k) => (
                  <kbd key={k}
                       className="font-mono px-1.5 py-0.5 rounded border border-mye-border bg-mye-app/60 text-[10px]">
                    {k}
                  </kbd>
                ))}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
