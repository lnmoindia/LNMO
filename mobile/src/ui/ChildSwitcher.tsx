// Header child switcher: avatar + name + class; opens a sheet when there are several children.
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { fonts } from "@/src/theme";
import { C } from "./kit";
import { Avatar, Sheet } from "./brandbits";
import { useChild } from "@/src/state/child";
import { useBrand } from "@/src/state/auth";
import { classLabel, fullName } from "@/src/lib/format";

export function ChildSwitcher() {
  const { children, child, setChild } = useChild();
  const [open, setOpen] = useState(false);
  const b = useBrand();
  if (!child) return null;
  const many = (children?.length || 0) > 1;
  return (
    <>
      <Pressable onPress={() => many && setOpen(true)} disabled={!many} testID="child-switcher"
        style={({ pressed }) => [s.pill, pressed && { opacity: 0.8 }]}>
        <Avatar name={child.first_name} size={32} />
        <View style={{ maxWidth: 110 }}>
          <Text style={s.name} numberOfLines={1}>{child.first_name}</Text>
          <Text style={s.cls} numberOfLines={1}>{classLabel(child)}</Text>
        </View>
        {many && <Feather name="chevron-down" size={16} color={C.muted} />}
      </Pressable>
      <Sheet open={open} onClose={() => setOpen(false)} title="Switch child" testID="child-switcher-sheet">
        {(children || []).map((c: any) => (
          <Pressable key={c.id} onPress={() => { setChild(c.id); setOpen(false); }} testID={`child-option-${c.id}`}
            style={({ pressed }) => [s.opt, c.id === child.id && { borderColor: b.color, backgroundColor: b.soft }, pressed && { opacity: 0.85 }]}>
            <Avatar name={c.first_name} size={44} />
            <View style={{ flex: 1 }}>
              <Text style={s.optName}>{fullName(c)}</Text>
              <Text style={s.cls}>{classLabel(c)}{c.admission_no ? ` · Adm. ${c.admission_no}` : ""}</Text>
            </View>
            {c.id === child.id && <Feather name="check-circle" size={22} color={b.ink} />}
          </Pressable>
        ))}
      </Sheet>
    </>
  );
}

const s = StyleSheet.create({
  pill: { flexDirection: "row", alignItems: "center", gap: 8, paddingLeft: 4, paddingRight: 10, minHeight: 44, borderRadius: 999, backgroundColor: C.surfaceSecondary, borderWidth: 1, borderColor: C.border },
  name: { fontFamily: fonts.bodyBold, fontSize: 13, color: C.onSurface },
  cls: { fontFamily: fonts.body, fontSize: 12, color: C.muted },
  opt: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: 18, borderWidth: 1.5, borderColor: C.border, marginBottom: 10, minHeight: 68 },
  optName: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
});
