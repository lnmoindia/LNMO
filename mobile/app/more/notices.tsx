import { useNotices } from "@/src/lib/queries";
import { StackScreen } from "@/src/ui/Screen";
import { Card, Empty, ErrorState, SkeletonList } from "@/src/ui/kit";
import { NoticeCard } from "@/src/parent/NoticeCard";

export default function Notices() {
  const q = useNotices();
  return (
    <StackScreen title="Notices" testID="notices-screen">
      {q.isLoading ? <SkeletonList n={3} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !q.data?.length
        ? <Card><Empty icon="bell" title="No notices" text="No notices from the school right now." testID="notices-empty" /></Card>
        : q.data.map((n: any) => <NoticeCard key={n.id} n={n} testID={`notice-${n.id}`} />)}
    </StackScreen>
  );
}
