import { Text, View } from "react-native";
import { router, type Href } from "expo-router";
import { useAuth } from "@/src/state/auth";
import { TabScreen } from "@/src/ui/Screen";
import { Card, Divider, ListRow, k, type IconName } from "@/src/ui/kit";
import { Avatar, confirm, PoweredBy } from "@/src/ui/brandbits";
import { switchView } from "@/src/state/view";
import { useOutboxCounts } from "@/src/offline/outbox";
import { signOutWarning } from "@/src/offline/warn";

type Item = [IconName, string, string, string];
const WORK: Item[] = [
  ["clock", "My timetable", "Week view", "/teacher/more/timetable"],
  ["repeat", "My substitutions", "Covers, history and leave request", "/teacher/more/substitutions"],
  ["users", "My class", "Students, parents, call / message", "/teacher/more/myclass"],
  ["edit-3", "Marks registers", "Assessments you can see (read-only)", "/teacher/more/marks"],
  ["credit-card", "Fee defaulters", "Your class (view only)", "/teacher/more/defaulters"],
  ["bell", "Notices", "From the school", "/more/notices"],
  ["upload-cloud", "Offline sync", "Registers saved offline", "/offline"],
];
const ME: Item[] = [
  ["user", "Profile", "Your details", "/teacher/more/profile"],
  ["bell", "Notifications", "Choose which alerts you get", "/more/notifications"],
  ["life-buoy", "Support", "Report an issue", "/more/support"],
  ["info", "About", "App version · Powered by LNMO", "/more/about"],
];
const Group = ({ items }: { items: Item[] }) => (
  <Card style={{ padding: 0, overflow: "hidden" }}>
    {items.map(([icon, title, sub, to], i) => (
      <View key={to}>{i > 0 && <Divider />}<ListRow icon={icon} title={title} sub={sub} onPress={() => router.push(to as Href)} testID={`tmore-${to.split("/").pop()}`} /></View>
    ))}
  </Card>
);

export default function TeacherMore() {
  const { logout, setSchool, school, user } = useAuth();
  const { waiting, attention } = useOutboxCounts();
  const sync = waiting + attention ? `${waiting} waiting${attention ? ` · ${attention} need attention` : ""}` : "";
  return (
    <TabScreen testID="teacher-more-screen" title="More" showSwitcher={false}>
      {user?.is_principal && (
        <Card style={{ padding: 0 }}>
          <ListRow icon="briefcase" title="Switch to Principal view" sub="Today, cover, attendance and fees for your divisions" onPress={() => switchView(user.id, "principal")} testID="tmore-switch-principal" />
        </Card>
      )}
      <Card onPress={() => router.push("/teacher/more/profile")} style={{ flexDirection: "row", alignItems: "center", gap: 14 }} testID="tmore-me-card">
        <Avatar name={user?.name || "T"} size={52} />
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={k.h2} numberOfLines={1}>{user?.name}</Text>
          <Text style={k.small} numberOfLines={1}>Teacher · {school?.name}</Text>
        </View>
      </Card>
      <Group items={WORK.map((it) => (it[3] === "/offline" && sync ? [it[0], it[1], sync, it[3]] : it)) as Item[]} />
      <Group items={ME} />
      <Card style={{ padding: 0, overflow: "hidden" }}>
        <ListRow icon="repeat" title="Change school" sub={school?.name} testID="tmore-change-school" onPress={async () => {
          if (await confirm("Change school?", `You'll be signed out.${signOutWarning()}`, "Change school")) { await logout(); await setSchool(null); router.replace("/school"); }
        }} />
        <Divider />
        <ListRow icon="log-out" title="Sign out" danger testID="tmore-sign-out" onPress={async () => {
          if (await confirm(signOutWarning() ? "Sign out anyway?" : "Sign out?", `You'll need your password to sign in again.${signOutWarning()}`, "Sign out")) { await logout(); router.replace("/login"); }
        }} />
      </Card>
      <PoweredBy testID="teacher-more-powered-by" />
    </TabScreen>
  );
}
