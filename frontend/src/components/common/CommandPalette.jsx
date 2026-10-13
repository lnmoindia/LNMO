import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import { DialogTitle } from "../ui/dialog";
import api from "../../lib/api";

export default function CommandPalette({ open, setOpen, nav }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [groups, setGroups] = useState([]);
  const timer = useRef(null);

  useEffect(() => {
    if (!open) { setQuery(""); setGroups([]); }
  }, [open]);

  useEffect(() => {
    clearTimeout(timer.current);
    if (query.trim().length < 2) { setGroups([]); return; }
    timer.current = setTimeout(() => {
      api.get("/search", { params: { q: query } })
        .then((r) => setGroups(r.data.groups || []))
        .catch(() => setGroups([]));
    }, 250);
    return () => clearTimeout(timer.current);
  }, [query]);

  const go = (path) => { setOpen(false); navigate(path); };
  const pages = nav.flatMap((g) => g.items);

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <DialogTitle className="sr-only">Global search</DialogTitle>
      <CommandInput placeholder="Search pages, people, records…" value={query} onValueChange={setQuery} data-testid="command-search-input" />
      <CommandList data-testid="command-results">
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Pages">
          {pages.map((p) => (
            <CommandItem key={p.path} value={`page ${p.label}`} onSelect={() => go(p.path)} data-testid={`command-page-${p.label.toLowerCase().replace(/\s+/g, "-")}`}>
              <p.icon size={14} className="mr-2 text-slate-400" /> {p.label}
            </CommandItem>
          ))}
        </CommandGroup>
        {groups.map((g) => (
          <CommandGroup key={g.label} heading={g.label}>
            {g.items.map((it) => (
              <CommandItem key={`${g.label}-${it.id}`} value={`${g.label} ${it.label} ${it.sub}`} onSelect={() => go(it.path)} data-testid={`command-result-${it.id}`}>
                <span>{it.label}</span>
                {it.sub && <span className="ml-2 text-xs text-slate-400">{it.sub}</span>}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
