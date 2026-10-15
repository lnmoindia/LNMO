// Locked accounts I may unlock (GET /account-locks is scoped by the server) + where to reset passwords.
import { Text } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { useToast } from "@/src/state/toast";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, Empty, ErrorState, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { fmtDateTime } from "@/src/lib/format";

export default function PUsers() {
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["p-locks"], queryFn: async () => { const d = await api.get("/account-locks"); return d.locks || d.items || (Array.isArray(d) ? d : []); } });
  const unlock = async (u: any) => { try { await api.post(`/account-locks/${u.user_id || u.id}/unlock`, {}); toast("Account unlocked"); qc.invalidateQueries({ queryKey: ["p-locks"] }); } catch (e: any) { toast(e.message, "error"); } };
  return (
    <StackScreen title="Users & passwords" testID="principal-users-screen">
      <SectionTitle title="Locked accounts" />
      {q.isLoading ? <SkeletonList n={1} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !q.data.length ? <Card><Empty icon="unlock" text="No locked accounts right now." testID="plocks-empty" /></Card>
        : q.data.map((u: any) => (
          <Card key={u.user_id || u.id} style={{ gap: 6 }} testID={`plock-${u.user_id || u.id}`}>
            <Text style={k.label}>{u.name || u.email}</Text><Text style={k.small}>{u.role} · locked {fmtDateTime(u.locked_at || u.at)}</Text>
            <Button small icon="unlock" label="Unlock" onPress={() => unlock(u)} testID={`plock-unlock-${u.user_id || u.id}`} />
          </Card>
        ))}
      <Text style={k.small}>To reset a password, open the person in Teachers or Students → Password. Admins and other principals are managed by the school admin.</Text>
    </StackScreen>
  );
}
