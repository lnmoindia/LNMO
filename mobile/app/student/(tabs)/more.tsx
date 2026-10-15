import { Text, View } from "react-native";
import { router, type Href } from "expo-router";
import { useAuth } from "@/src/state/auth";
import { useMe } from "@/src/lib/queries";
import { TabScreen } from "@/src/ui/Screen";
import { Card, Divider, ListRow, k, type IconName } from "@/src/ui/kit";
import { confirm, PoweredBy } from "@/src/ui/brandbits";

type Item = [IconName, string, string, string];
const STUDY: Item[] = [
  ["calendar", "Exams", "Upcoming schedule", "/student/more/exams"],
  ["award", "Results", "Scores, subjects and trends", "/student/more/results"],
  ["check-square", "Attendance", "Month calendar", "/student/more/attendance"],
  ["bell", "Notices", "From the school", "/more/notices"],
  ["book", "Library", "Approved study materials", "/student/more/library"],
];
const ME: Item[] = [
  ["credit-card", "Fees", "Your fee summary and receipts", "/student/more/fees"],
  ["star", "Achievements", "Recorded by your teachers", "/student/more/achievements"],
  ["user", "Profile", "Your details and photo", "/student/more/profile"],
  ["bell", "Notifications", "Choose which alerts you get", "/more/notifications"],
  ["life-buoy", "Support", "Report an issue to the school", "/more/support"],
  ["info", "About", "App version · Powered by LNMO", "/more/about"],
];

const Group = ({ items }: { items: Item[] }) => (
  <Card style={{ padding: 0, overflow: "hidden" }}>
    {items.map(([icon, title, sub, to], i) => (
      <View key={to}>{i > 0 && <Divider />}
        <ListRow icon={icon} title={title} sub={sub} onPress={() => router.push(to as Href)} testID={`smore-${to.split("/").pop()}`} />
      </View>
    ))}
  </Card>
);

export default function StudentMore() {
  const { logout, setSchool, school } = useAuth();
  const me = useMe();
  const changeSchool = async () => {
    if (!(await confirm("Change school?", "You'll be signed out and can pick a different school.", "Change school"))) return;
    await logout(); await setSchool(null); router.replace("/school");
  };
  const signOut = async () => {
    if (!(await confirm("Sign out?", "You'll need your password to sign in again.", "Sign out"))) return;
    await logout(); router.replace("/login");
  };
  return (
    <TabScreen testID="student-more-screen" title="More" showSwitcher={false}>
      {me.data?.student && <Text style={k.small}>{me.data.student.first_name} · {me.data.student.class_name} {me.data.student.section || ""}</Text>}
      <Group items={STUDY} />
      <Group items={ME} />
      <Card style={{ padding: 0, overflow: "hidden" }}>
        <ListRow icon="repeat" title="Change school" sub={school?.name} onPress={changeSchool} testID="smore-change-school" />
        <Divider />
        <ListRow icon="log-out" title="Sign out" onPress={signOut} danger testID="smore-sign-out" />
      </Card>
      <PoweredBy testID="student-more-powered-by" />
    </TabScreen>
  );
}
