// Linked children + the selected child (persisted), shared by every parent screen.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { storage } from "@/src/utils/storage";
import { useAuth } from "./auth";

const KEY = "lnmo.child";
type Ctx = { children: any[] | null; child: any | null; childId: string; setChild: (id: string) => void; reload: () => void; error: any };
const ChildCtx = createContext<Ctx | null>(null);

export function ChildProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const enabled = user?.role === "parent" && !user?.must_change_password;
  const q = useQuery({ queryKey: ["children"], queryFn: () => api.get("/parent/children"), enabled });
  const [picked, setPicked] = useState<string>("");
  useEffect(() => { storage.getItem(KEY, "").then((v) => setPicked((v as string) || "")); }, []);
  const list = q.data?.children ?? (q.isError ? [] : null);
  const child = useMemo(() => (list?.length ? list.find((c: any) => c.id === picked) || list[0] : null), [list, picked]);
  const setChild = useCallback((id: string) => { setPicked(id); storage.setItem(KEY, id); }, []);
  const value = { children: enabled ? list : null, child, childId: child?.id || "", setChild, reload: () => q.refetch(), error: q.error };
  return <ChildCtx.Provider value={value}>{children}</ChildCtx.Provider>;
}

export function useChild() {
  const c = useContext(ChildCtx);
  if (!c) throw new Error("useChild outside ChildProvider");
  return c;
}
