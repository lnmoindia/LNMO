import { Text, View } from "react-native";
import { router, type Href } from "expo-router";
import { useAuth } from "@/src/state/auth";
import { useChild } from "@/src/state/child";
import { TabScreen } from "@/src/ui/Screen";
import { Card, Divider, ListRow, IconName, k } from "@/src/ui/kit";
import { confirm, PoweredBy } from "@/src/ui/brandbits";
import { fullName } from "@/src/lib/format";

type Item = [IconName, string, string, string];
const CHILD: Item[] = [
  ["book-open", "Homework", "Due, submitted and overdue work", "/more/homework"],
  ["check-square", "Attendance", "Month calendar", "/more/attendance"],
  ["award", "Results", "Exams, scores and trends", "/more/results"],
  ["bell", "Notices", "From the school", "/more/notices"],
  ["star", "Achievements", "Recorded by the class teacher", "/more/achievements"],
  ["user", "Child profile", "Admission, class and details", "/more/profile"],
];
const ACCOUNT: Item[] = [
  ["users", "My account", "Your details and linked children", "/more/account"],
  ["bell", "Notifications", "Choose which alerts you get", "/more/notifications"],
  ["life-buoy", "Support", "Report an issue to the school", "/more/support"],
  ["info", "About", "App version · Powered by LNMO", "/more/about"],
];

const Group = ({ items, prefix }: { items: Item[]; prefix: string }) => (
  <Card style={{ padding: 0, overflow: "hidden" }}>
    {items.map(([icon, title, sub, to], i) => (
      <View key={to}>
        {i > 0 && <Divider />}
        <ListRow icon={icon} title={title} sub={sub} onPress={() => router.push(to as Href)} testID={`${prefix}-${to.split("/").pop()}`} />
      </View>
    ))}
  </Card>
);

export default function More() {
  const { logout, setSchool, school } = useAuth();
  const { child } = useChild();
  const changeSchool = async () => {
    if (!(await confirm("Change school?", "You'll be signed out and can pick a different school.", "Change school"))) return;
    await logout(); await setSchool(null); router.replace("/school");
  };
  const signOut = async () => {
    if (!(await confirm("Sign out?", "You'll need your password to sign in again.", "Sign out"))) return;
    await logout(); router.replace("/login");
  };
  return (
    <TabScreen testID="more-screen" title="More">
      {child && <Text style={k.small}>About {fullName(child)}</Text>}
      <Group items={CHILD} prefix="more" />
      <Group items={ACCOUNT} prefix="more" />
      <Card style={{ padding: 0, overflow: "hidden" }}>
        <ListRow icon="repeat" title="Change school" sub={school?.name} onPress={changeSchool} testID="more-change-school" />
        <Divider />
        <ListRow icon="log-out" title="Sign out" onPress={signOut} danger testID="more-sign-out" />
      </Card>
      <PoweredBy testID="more-powered-by" />
    </TabScreen>
  );
}
