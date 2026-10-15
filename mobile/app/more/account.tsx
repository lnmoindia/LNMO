import { Text, View } from "react-native";
import { router } from "expo-router";
import { useAuth } from "@/src/state/auth";
import { useChild } from "@/src/state/child";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, Divider, Empty, Field, ListRow, SectionTitle, k } from "@/src/ui/kit";
import { confirm } from "@/src/ui/brandbits";
import { MyPhotoCard } from "@/src/ui/MyPhoto";
import { classLabel, fullName } from "@/src/lib/format";

export default function Account() {
  const { user } = useAuth();
  const { children, reload } = useChild();
  const toast = useToast();
  const unlink = async (c: any) => {
    if (!(await confirm("Unlink child?", `Remove ${c.first_name} from your account? You can link again later.`, "Unlink"))) return;
    try { await api.post(`/parent/unlink/${c.id}`); toast("Child unlinked"); reload(); } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <StackScreen title="My account" testID="account-screen">
      <MyPhotoCard />
      <Card testID="account-details">
        <Field label="Name" value={user?.name} testID="account-name" />
        <Field label="Login email" value={user?.email} testID="account-email" />
        {user?.phone ? <Field label="Mobile" value={user.phone} /> : null}
        <Field label="School" value={user?.institution_name} />
      </Card>
      <SectionTitle title="Linked children" action="Link a child" onAction={() => router.push("/more/link-child")} testID="account-link-child-btn" />
      <Card style={{ padding: 0 }} testID="account-children">
        {!children?.length ? <Empty icon="users" text="No children linked yet. Use Link a child with the admission number and your registered mobile." /> : children.map((c: any, i: number) => (
          <View key={c.id}>
            {i > 0 && <Divider />}
            <ListRow icon="user" title={fullName(c)} sub={`${classLabel(c)}${c.admission_no ? ` · Adm. ${c.admission_no}` : ""}`}
              right={<Button small variant="ghost" label="Unlink" onPress={() => unlink(c)} testID={`account-unlink-${c.id}`} />} />
          </View>
        ))}
      </Card>
      <Text style={k.small}>To change your password or contact details, ask the school office.</Text>
    </StackScreen>
  );
}
