import { router } from "expo-router";
import { Text, View } from "react-native";
import { useAuth } from "@/src/state/auth";
import { TabScreen } from "@/src/ui/Screen";
import { Card, Divider, ListRow, k, type IconName } from "@/src/ui/kit";
import { Avatar, confirm, PoweredBy } from "@/src/ui/brandbits";
import { ViewSwitch } from "@/src/ui/ViewSwitch";
import { signOutWarning } from "@/src/offline/warn";

type Item = [IconName, string, string, string];
const WORK: Item[] = [
  ["message-circle", "Parent messages", "Inbox and live chat", "/principal/messages"],
  ["book-open", "Homework & assignments", "Submissions, review and redo", "/principal/work"],
  ["search", "Students", "Search by name or admission no", "/principal/students"],
  ["users", "Teachers", "Contacts and timetables", "/principal/teachers"],
  ["bell", "Notices", "Read and post notices", "/principal/notices"],
  ["lock", "Users & passwords", "Unlock accounts, reset passwords", "/principal/users"],
];
const ME: Item[] = [
  ["user", "Profile", "Photo and teaching load", "/teacher/more/profile"],
  ["bell", "Notifications", "Choose which alerts you get", "/more/notifications"],
  ["upload-cloud", "Offline sync", "Registers saved offline", "/offline"],
  ["life-buoy", "Support", "Report an issue", "/more/support"],
  ["info", "About", "Version and server", "/more/about"],
];

const Group = ({ items }: { items: Item[] }) => (
  <Card style={{ padding: 0 }}>
    {items.map(([icon, title, sub, href], i) => (
      <View key={title}>{i > 0 && <Divider />}<ListRow icon={icon} title={title} sub={sub} onPress={() => router.push(href as any)} testID={`pmore-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`} /></View>
    ))}
  </Card>
);

export default function PrincipalMore() {
  const { logout, setSchool, school, user } = useAuth();
  return (
    <TabScreen testID="principal-more-screen" title="More" showSwitcher={false}>
      <ViewSwitch current="principal" />
      <Card style={{ flexDirection: "row", alignItems: "center", gap: 14 }} testID="pmore-me-card">
        <Avatar name={user?.name || "P"} size={52} />
        <View style={{ flex: 1, gap: 2 }}><Text style={k.h2} numberOfLines={1}>{user?.name}</Text><Text style={k.small} numberOfLines={1}>{user?.principal?.designation || "Principal"} · {school?.name}</Text></View>
      </Card>
      <Group items={WORK} />
      <Group items={ME} />
      <Card style={{ padding: 0 }}>
        <ListRow icon="refresh-cw" title="Change school" onPress={async () => { if (await confirm("Change school?", `You'll be signed out.${signOutWarning()}`, "Change school")) { await logout(); await setSchool(null); router.replace("/school"); } }} testID="pmore-change-school" />
        <Divider />
        <ListRow icon="log-out" title="Sign out" danger onPress={async () => { if (await confirm(signOutWarning() ? "Sign out anyway?" : "Sign out?", `You'll need your password to sign in again.${signOutWarning()}`, "Sign out")) { await logout(); router.replace("/login"); } }} testID="pmore-signout-btn" />
      </Card>
      <PoweredBy />
    </TabScreen>
  );
}
