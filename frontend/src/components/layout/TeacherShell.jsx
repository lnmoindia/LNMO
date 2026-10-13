import AppShell from "./AppShell";
import { teacherNav, buildPrincipalNav } from "../../navigation";
import { useAuth } from "../../context/AuthContext";
import { useSchoolBrand } from "../../pages/portal/useSchoolBrand";

// The /teacher mount. A plain teacher sees the teacher workspace; an elevated teacher (principal)
// sees the merged principal+teacher sidebar so both prefixes (/teacher/* and /app/*) feel like one app.
export default function TeacherShell() {
  const { user } = useAuth();
  const isPrincipal = Boolean(user?.is_principal);
  const brand = useSchoolBrand(isPrincipal ? "Principal Console" : "Teacher Portal");
  return (
    <AppShell
      nav={isPrincipal ? buildPrincipalNav(user) : teacherNav}
      consoleLabel={isPrincipal ? "Principal Console" : "Teacher Workspace"}
      brand={brand.loaded ? brand : null}
    />
  );
}
