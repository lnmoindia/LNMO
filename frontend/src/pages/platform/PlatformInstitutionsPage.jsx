import { useNavigate } from "react-router-dom";
import { Settings2 } from "lucide-react";
import ResourcePage from "../../components/common/ResourcePage";
import { institutionsConfig } from "./config";

export default function PlatformInstitutionsPage() {
  const navigate = useNavigate();
  return (
    <ResourcePage
      {...institutionsConfig}
      rowActions={[{ title: "Manage / Branding", icon: Settings2, testId: "manage-institution-btn", onClick: (row) => navigate(`/platform/institutions/${row.id}`) }]}
    />
  );
}
