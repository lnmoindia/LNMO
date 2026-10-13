import { forwardRef, useEffect, useRef, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "../ui/input";

// Password field with an accessible show/hide toggle; re-hides on form submit or when resetKey changes.
export const PasswordInput = forwardRef(({ className = "", resetKey, ...props }, ref) => {
  const [show, setShow] = useState(false);
  const inner = useRef(null);
  useEffect(() => { setShow(false); }, [resetKey]);
  useEffect(() => {
    const form = inner.current?.form;
    if (!form) return undefined;
    const hide = () => setShow(false);
    form.addEventListener("submit", hide);
    return () => form.removeEventListener("submit", hide);
  }, []);
  const setRef = (el) => {
    inner.current = el;
    if (typeof ref === "function") ref(el);
    else if (ref) ref.current = el;
  };
  const tid = props["data-testid"] || "password";
  return (
    <div className="relative">
      <Input ref={setRef} {...props} type={show ? "text" : "password"} autoCapitalize="none" autoCorrect="off" spellCheck={false} className={`pr-11 ${className}`} />
      <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}
        data-testid={`${tid}-toggle`}
        className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 rounded-md flex items-center justify-center text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-colors">
        {show ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
});
PasswordInput.displayName = "PasswordInput";
